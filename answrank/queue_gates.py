"""E13: ÇOK-KAPILI OTOMATİK ONAY DENETİMİ — DM gönderimini güvenli kılmak.

İnsan-döngü %37,5'ten %25'e düşürmenin riskli yarısı: DM onayı + gönderiminin
otomatikleşmesi. Bu modül onayı KALDIRMAZ — onay ancak N bağımsız denetimden
geçerse 'AUTO_APPROVED' olarak işaretlenir; her denetim nedeniyle yazar.

Kapılar (hepsi geçmeli):
  1. ölçüm-var: domain için GERÇEK görünürlük ölçümü kayıtlı (total>0)
  2. mini-probe-var: robots/llms/bots ölçülmüş (measured=1)
  3. taze-ölçüm: ölçüm son N gün içinde (varsayılan 7)
  4. iletişim-doğrulandı: telefondan VEYA e-postadan en az biri kanıtlanmış;
     DOĞRULANAMADI ile karanlık-açık gönderim yapmaz
  5. tekerrür-yok: aynı domain'e son N gün içinde DM gönderilmemiş veya
     onay taahhüdü verilmiş (gerçek gönderim + onay birleşik kanıt)
  6. içerik-izlenebilir: DM'deki her sayı bir veritabanı satırından gelir
     (uydurma kanıt yok — E5/E7)

Sonuç: AUTO_APPROVED durumunda bile DM gönderimi için onay gerekir (gönderim
kanalı ayrı); bu modül yalnızca insanın HER BİR maddeye tek tek bakma
yükünü azaltır — kuralları geçemeyenler PENDING'de kalır, insanı bekler.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from answrank.db import Database

FRESH_DAYS = 7
REPEAT_DAYS = 14


class GateResult:
    """Tek bir denetim kapısının sonucu."""

    def __init__(self, name: str, passed: bool, reason: str):
        self.name = name
        self.passed = passed
        self.reason = reason

    def to_dict(self) -> Dict:
        """Kural parametrelerini sözlük olarak döndürür."""
        return {"gate": self.name, "passed": self.passed, "reason": self.reason}


class DmGateAuditor:
    """DM kuyruk maddeleri için bağımsız denetim kapıları."""

    def __init__(self, db: Optional[Database] = None,
                 fresh_days: int = FRESH_DAYS,
                 repeat_days: int = REPEAT_DAYS):
        self.db = db or Database()
        self.fresh_days = fresh_days
        self.repeat_days = repeat_days

    # ------------------------------------------------------------------ kapılar
    def _gate_measurement(self, domain: str) -> GateResult:
        vis = self.db_visibility(domain)
        if not vis:
            return GateResult("ölçüm-var", False,
                              "son koşuda doğrulanabilir tam-canlı kanıt YOK "
                              "(kayıt eksik, simülasyon veya tutarsızlık) — DM kanıtsız")
        return GateResult("ölçüm-var", True,
                          f"{vis['total']} sorgu / {vis['hits']} vuruş (tam-canlı)")

    def _gate_probe(self, domain: str) -> GateResult:
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT verdict, measured FROM miniprobe_leads"
                " WHERE domain = ? AND measured = 1 ORDER BY id DESC LIMIT 1",
                (domain,)).fetchone()
        if not row:
            return GateResult("mini-probe-var", False,
                              "mini-probe ölçülmedi — erişim kanıtı yok")
        return GateResult("mini-probe-var", True, f"hüküm: {row['verdict']}")

    def _gate_fresh(self, domain: str) -> GateResult:
        # Tazelik ortak doğrulanmış kayıttan gelir (aynı kayıt DM kanıtıdır);
        # ayrı sorgu yok, eski/bozuk koşuya dönüş yok.
        vis = self.db_visibility(domain)
        if not vis:
            return GateResult("taze-ölçüm", False,
                              "doğrulanabilir son kanıt yok (tazeliği belirsiz)")
        try:
            created = datetime.fromisoformat(vis["created_at"])
        except (TypeError, ValueError):
            return GateResult("taze-ölçüm", False, "ölçüm tarihi okunamadı")
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if created > now:
            return GateResult("taze-ölçüm", False,
                              "ölçüm tarihi gelecekte — kanıt anormalliği")
        age = now - created
        if age > timedelta(days=self.fresh_days):
            return GateResult("taze-ölçüm", False,
                              f"ölçüm {age.days} gün önce — taze değil")
        return GateResult("taze-ölçüm", True, f"{age.days} gün önce ölçüldü")

    def _gate_contact(self, domain: str) -> GateResult:
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT phone, email FROM prospects WHERE domain_ref = ?"
                " ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
        if not row:
            return GateResult("iletişim-doğrulandı", False,
                              "kayıtlı aday yok — alıcı belirsiz")
        have = [x for x in (row["phone"], row["email"]) if x and x.strip()
                and "DOĞRULANAMADI" not in x.upper()]
        if not have:
            return GateResult("iletişim-doğrulandı", False,
                              "telefon ve e-posta DOĞRULANAMADI — karanlık gönderim")
        return GateResult("iletişim-doğrulandı", True,
                          f"kanıtlandı: {' + '.join(have[:2])}")

    def _gate_repeat(self, domain: str) -> GateResult:
        """Tekerrür kapısı İKİ kanıtı birleştirir: gerçek gönderim (dm_send_log)
        ve onay taahhüdü (approval_queue AUTO_APPROVED/APPROVED).

        Onaylanan sözleşme: yakın onay taahhüdü 'zaten onaylandı' ile kapıyı
        kapatır; gerçek gönderim 'zaten gönderildi' ile kapatır. Aynı tazelişte
        gerçek gönderim önceliklidir (daha güçlü temas kanıtı). Belirsiz SMTP
        girişimi (HATA) da temas sayılır — fail-closed tekerrürü kapatır."""
        with self.db._get_connection() as conn:
            send = conn.execute(
                "SELECT status, sent_at FROM dm_send_log WHERE domain=?"
                " AND status IN ('GÖNDERİLDİ','HATA')"
                " ORDER BY sent_at DESC LIMIT 1", (domain,)).fetchone()
            promised = conn.execute(
                "SELECT decided_at FROM approval_queue WHERE kind='DM' AND ref_id=?"
                " AND status IN ('AUTO_APPROVED','APPROVED') AND decided_at IS NOT NULL"
                " ORDER BY decided_at DESC LIMIT 1", (domain,)).fetchone()
        candidates = []
        for source, stamp in (("gönderim", send["sent_at"] if send else None),
                              ("onay", promised["decided_at"] if promised else None)):
            if not stamp:
                continue
            try:
                dt = datetime.fromisoformat(stamp)
            except (TypeError, ValueError):
                return GateResult("tekerrür-yok", False, "önceki gönderim tarihi okunamadı")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            candidates.append((dt, source))
        if not candidates:
            return GateResult("tekerrür-yok", True, "önceki gönderim yok")
        # Eşit tazelikte gerçek gönderim kazanır (daha güçlü temas kanıtı).
        last, source = max(candidates,
                           key=lambda c: (c[0], 1 if c[1] == "gönderim" else 0))
        if datetime.now(timezone.utc) - last < timedelta(days=self.repeat_days):
            why = (f"son {self.repeat_days} gün içinde zaten gönderildi"
                   if source == "gönderim"
                   else f"son {self.repeat_days} gün içinde zaten onaylandı")
            return GateResult("tekerrür-yok", False, why)
        return GateResult("tekerrür-yok", True, "önceki gönderim eski")

    def _gate_traceable(self, domain: str, dm_text: str) -> GateResult:
        """DM'deki her SAYI bir ölçüm kaydından gelmeli (uydurma yok).

        İzinli sayılar yalnızca doğrulanmış son koşudan (total, hits, fark,
        yüzde) ve o kaydın koşu kimliği/tarih damgasından üretilir;
        mini-probe '3/3' satırı ve sabit '360' ürün adı ayrıca izinlidir."""
        import re
        if not dm_text:
            return GateResult("içerik-izlenebilir", False, "DM metni boş")
        vis = self.db_visibility(domain)
        if not vis:
            return GateResult("içerik-izlenebilir", False,
                              "sayıların eşleştirileceği doğrulanmış ölçüm yok")
        with self.db._get_connection() as conn:
            probe = conn.execute(
                "SELECT bots_line FROM miniprobe_leads WHERE domain = ?"
                " AND measured = 1 ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
        total, found = vis["total"], vis["hits"]
        pct = round(100 * found / total, 1) if total else 0.0
        # yüzde iki biçimde yazılır: '50' veya '50.0'
        pct_parts = {str(int(pct)), str(pct)}
        legit = {str(total), str(found), str(total - found)}
        legit |= {p for p in pct_parts if p != "0"}
        legit.add("360")  # 360° ürün adı
        if probe and "3/3" in (probe["bots_line"] or ""):
            legit.add("3")
        # Damga/koşu kimliği yalnız KENDİ tokenı olarak kanıttır: alt-dizgi
        # eşleşmesi uydurma sayıyı meşrulaştıramaz (mikrosaniye rastgeledir),
        # tam token çıkarıldıktan sonra kalan sayılar denetlenir.
        clean = dm_text
        for token in (str(vis["created_at"]), str(vis["run_id"])):
            clean = re.sub(rf"(?<!\w){re.escape(token)}(?!\w)", "", clean)
        digits = re.sub(r"\D+", "", vis["created_at"])
        probe_line = (probe["bots_line"] or "") if probe else ""
        stray = set()
        for n in set(re.findall(r"\d+", clean)):
            if n in legit or n == digits:
                continue
            if len(n) == 1 and (n in digits or "3" in probe_line):
                continue  # tek hane: tarih parçası veya probe '3/3' yazımı
            stray.add(n)
        if stray:
            return GateResult("içerik-izlenebilir", False,
                              f"izlenemeyen sayı: {sorted(stray)[:3]}")
        return GateResult("içerik-izlenebilir", True,
                          f"her sayı doğrulanmış ölçümden (koşu {vis['run_id']})")

    # ------------------------------------------------------------------ denetim
    def audit(self, domain: str, dm_text: str = "", log: bool = True) -> Dict:
        """Tüm kapıları çalıştır; hepsi geçmeli. İlk failure'da durmaz —
        insan nedenlerin TAMAMINI görmeli (karar için). Sonuçları kalıcı
        denetim defterine yazar (log=True)."""
        gates = [
            self._gate_measurement(domain),
            self._gate_probe(domain),
            self._gate_fresh(domain),
            self._gate_contact(domain),
            self._gate_repeat(domain),
            self._gate_traceable(domain, dm_text),
        ]
        all_passed = all(g.passed for g in gates)
        out = {"domain": domain, "all_passed": all_passed,
               "gates": [g.to_dict() for g in gates]}
        if log:
            self._log(domain, out["gates"], all_passed)
        return out

    def _log(self, domain: str, gates: List[Dict], all_passed: bool) -> None:
        """Denetim izi — her kapı nedeniyle yazılır; karar için kanıt."""
        now = datetime.now(timezone.utc).isoformat()
        with self.db._get_connection() as conn:
            for g in gates:
                conn.execute(
                    "INSERT INTO gate_audit_log"
                    " (domain, gate, passed, reason, all_passed, created_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (domain, g["gate"], 1 if g["passed"] else 0,
                     g["reason"], 1 if all_passed else 0, now))
            conn.commit()

    def audit_pending(self) -> List[Dict]:
        """Tüm PENDING DM maddelerini GERÇEK gövde metniyle denetle.

        Boş-metin denetimi sahte 'DM metni boş' izi üretir; auto_approve
        ile aynı metni kullanır (tek denetim, çift iz yok)."""
        from answrank.crm.outreach import OutreachGenerator
        out = []
        with self.db._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, ref_id, summary FROM approval_queue"
                " WHERE kind='DM' AND status='PENDING' ORDER BY id").fetchall()
        for r in rows:
            lead = self.db.latest_measured_lead(r["ref_id"])
            if lead:
                vis = self.db_visibility(r["ref_id"])
                dm = OutreachGenerator.lead_dm(
                    lead["domain"], lead["robots_line"], lead["llms_line"],
                    lead["bots_line"], lead["verdict"], ai_visibility=vis)
            else:
                vis, dm = None, ""
            out.append({"id": r["id"], "evidence_run_id": vis["run_id"] if vis else None,
                        **self.audit(r["ref_id"], dm_text=dm)})
        return out

    # ---------------------------------------------------- denetim-geçmiş onay
    def auto_approve(self, dry_run: bool = True) -> Dict:
        """Yalnızca TÜM kapıları geçen DM maddelerini AUTO_APPROVED yapar.

        Bu onayı KALDIRMAZ — makine kararını insan kararından AYRI işaretler
        (AUTO_APPROVED). Gönderim yine ayrı bir insan/denetim kanalıdır.
        audit_pending zaten gerçek gövde metniyle tek denetim yazar; burada
        ikinci denetim yok. İnsan-kararı yarışı koşullu UPDATE'in rowcount
        kontrolüyle çözülür: karar deşmişse otomatik onay uygulanmaz."""
        items = self.audit_pending()
        approved, blocked = [], []
        for item in items:
            lead = self.db.latest_measured_lead(item["domain"])
            if not lead:
                blocked.append({"id": item["id"], "domain": item["domain"],
                                "why": "mini-probe lead kaydı yok"})
                continue
            if not item["all_passed"]:
                blocked.append({"id": item["id"], "domain": item["domain"],
                                "gates": item["gates"]})
                continue
            approved.append({"id": item["id"], "domain": item["domain"]})
        conflicts = []
        if not dry_run:
            now = datetime.now(timezone.utc).isoformat()
            applied = []
            with self.db._get_connection() as conn:
                for a in approved:
                    changed = conn.execute(
                        "UPDATE approval_queue SET status='AUTO_APPROVED',"
                        " decided_at=?, decision_note=?, evidence_run_id=?"
                        " WHERE id=? AND status='PENDING'",
                        (now, "çok-kapılı denetim: 6/6 geçti",
                         a.get("evidence_run_id"), a["id"]))
                    if changed.rowcount == 1:
                        applied.append(a)
                    else:
                        conflicts.append({**a, "why": "Karar değişti; otomatik onay uygulanmadı"})
                conn.commit()
            approved = applied
        return {"dry_run": dry_run, "auto_approved": approved,
                "still_pending": blocked, "conflicts": conflicts}

    def db_visibility(self, domain: str) -> Optional[dict]:
        """CLI ve gönderim ile aynı son-koşu kanıtını kullanır."""
        return self.db.get_dm_visibility(domain)
