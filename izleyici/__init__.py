"""izleyici — AEO görünürlük izleyici (AnswRank motoru üstüne ince katman).

Motor (`ai_gorunurluk.py`) DEĞİŞTİRİLMEZ: ölçüm fonksiyonları salt-okunur
kullanılır. Bu paket yalnızca şunları ekler:
  - takip listesi yönetimi (hangi alan adları izleniyor)
  - tarihli snapshot saklama (motor'un üzerine-yazan kaydından farklı olarak
    her koşu ayrı dosyaya yazılır → zaman serisi oluşur)
  - iki snapshot arasındaki delta'nın insan-okur rapora çevrilmesi

CLI:  python3 -m izleyici add|list|remove|run|delta
"""
