"""Script to generate 5 high-end bespoke SVG logos for AnswRank and render them to 1024x1024 PNGs."""

import os
import subprocess

OUT_DIR = "/home/gokun/projects/02_sahis/85-AnswRank/assets/logos"
ARTIFACT_DIR = "/home/gokun/.gemini/antigravity-ide/brain/789df58b-8854-4d81-bb65-2d233ec1d40d/logos"

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(ARTIFACT_DIR, exist_ok=True)

# Logo 1: The Citation Monogram ("The Quotation Apex")
# Swiss Minimalist style, Emerald & Titanium White on Obsidian Black
svg_1 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <linearGradient id="bg1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#08090d"/>
      <stop offset="100%" stop-color="#10121a"/>
    </linearGradient>
    <linearGradient id="emeraldGrad" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#059669"/>
      <stop offset="50%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#34d399"/>
    </linearGradient>
    <linearGradient id="whiteGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#94a3b8"/>
    </linearGradient>
    <filter id="glow1" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="16" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="800" height="800" fill="url(#bg1)" rx="32"/>

  <!-- Subtle Blueprint Grid -->
  <g opacity="0.04" stroke="#ffffff" stroke-width="1">
    <line x1="200" y1="0" x2="200" y2="800"/>
    <line x1="400" y1="0" x2="400" y2="800"/>
    <line x1="600" y1="0" x2="600" y2="800"/>
    <line x1="0" y1="200" x2="800" y2="200"/>
    <line x1="0" y1="400" x2="800" y2="400"/>
    <line x1="0" y1="600" x2="800" y2="600"/>
    <circle cx="400" cy="360" r="180" fill="none"/>
  </g>

  <!-- Icon Mark: Geometric A fused with Citation Quotation & Arrow -->
  <g transform="translate(400, 340)">
    <!-- Left Stem of A / Open Quotation Hook -->
    <path d="M -90,140 L -90,-20 C -90,-80 -40,-130 20,-130 L 20,-75 C -10,-75 -35,-50 -35,-20 L -35,140 Z" 
          fill="url(#whiteGrad)"/>
    
    <!-- Right Upward Citation Arrow / Ascender (Emerald) -->
    <path d="M 35,140 L 35,-40 L 90,15 L 90,-90 L 0,-180 L -30,-150 L 35,-85 Z" 
          fill="url(#emeraldGrad)" filter="url(#glow1)"/>
    
    <!-- Central Crossbar / Horizontal Citation Dot -->
    <circle cx="-5" cy="50" r="16" fill="#10b981"/>
    <rect x="-35" y="44" width="70" height="12" rx="6" fill="#10b981" opacity="0.8"/>
  </g>

  <!-- Brand Typography -->
  <text x="400" y="610" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif" 
        font-size="44" font-weight="800" letter-spacing="8" fill="#ffffff">
    ANSW<tspan fill="#10b981">RANK</tspan>
  </text>
  
  <text x="400" y="655" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif" 
        font-size="14" font-weight="600" letter-spacing="4" fill="#64748b">
    ANSWER ENGINE OPTIMIZATION
  </text>
</svg>
"""

# Logo 2: The Semantic Spectrum (Converging LLM Consensus)
# Cobalt Blue, Cyan & Electric Indigo on Deep Slate
svg_2 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <linearGradient id="bg2" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#050814"/>
      <stop offset="100%" stop-color="#0d1424"/>
    </linearGradient>
    <linearGradient id="blueGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#1d4ed8"/>
      <stop offset="100%" stop-color="#38bdf8"/>
    </linearGradient>
    <linearGradient id="cyanGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#0284c7"/>
      <stop offset="100%" stop-color="#06b6d4"/>
    </linearGradient>
    <filter id="glow2" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="12" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <rect width="800" height="800" fill="url(#bg2)" rx="32"/>

  <!-- Icon: Converging Search Vectors to #1 Rank Node -->
  <g transform="translate(400, 340)">
    <!-- Outer ambient ring -->
    <circle cx="0" cy="0" r="160" stroke="#1e293b" stroke-width="2" stroke-dasharray="8 8" fill="none" opacity="0.6"/>
    
    <!-- Tier 3 Stream: Input Context -->
    <path d="M -140,80 L -40,80 L 20,20 L 100,20" stroke="#334155" stroke-width="8" stroke-linecap="round" fill="none"/>
    
    <!-- Tier 2 Stream: LLM Processing -->
    <path d="M -160,0 L -20,0 L 40,-20 L 120,-20" stroke="url(#cyanGrad)" stroke-width="12" stroke-linecap="round" fill="none"/>

    <!-- Tier 1 Stream: Cited Authority (#1 Rank) -->
    <path d="M -140,-80 L 0,-80 L 60,-40 L 140,-40" stroke="url(#blueGrad)" stroke-width="16" stroke-linecap="round" fill="none" filter="url(#glow2)"/>

    <!-- Focal Citation Diamond -->
    <polygon points="120,-40 145,-65 170,-40 145,-15" fill="#38bdf8" filter="url(#glow2)"/>
    <circle cx="145" cy="-40" r="5" fill="#ffffff"/>
  </g>

  <!-- Typography -->
  <text x="400" y="605" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif" 
        font-size="46" font-weight="700" letter-spacing="6" fill="#f8fafc">
    ANSW<tspan fill="#38bdf8">RANK</tspan>
  </text>
  
  <text x="400" y="650" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif" 
        font-size="13" font-weight="600" letter-spacing="5" fill="#475569">
    AI CITATION &amp; VISIBILITY INTELLIGENCE
  </text>
</svg>
"""

# Logo 3: The Precision Sextant / Ground Truth (Champagne Gold & Titanium on Matte Graphite)
# Architectural, Sovereign, High-Trust Advisory feel
svg_3 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <linearGradient id="bg3" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#111215"/>
      <stop offset="100%" stop-color="#18191f"/>
    </linearGradient>
    <linearGradient id="goldGrad" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#9a7b2c"/>
      <stop offset="50%" stop-color="#d4af37"/>
      <stop offset="100%" stop-color="#fef08a"/>
    </linearGradient>
  </defs>

  <rect width="800" height="800" fill="url(#bg3)" rx="32"/>

  <!-- Icon: Precision Optical Sextant & Vertex -->
  <g transform="translate(400, 330)">
    <!-- Fine geometric circles -->
    <circle cx="0" cy="0" r="140" stroke="#27272a" stroke-width="1.5" fill="none"/>
    <circle cx="0" cy="0" r="110" stroke="url(#goldGrad)" stroke-width="2" fill="none" opacity="0.7"/>
    
    <!-- Quadrant ticks -->
    <line x1="0" y1="-140" x2="0" y2="-125" stroke="#d4af37" stroke-width="3"/>
    <line x1="0" y1="140" x2="0" y2="125" stroke="#d4af37" stroke-width="3"/>
    <line x1="-140" y1="0" x2="-125" y2="0" stroke="#d4af37" stroke-width="3"/>
    <line x1="140" y1="0" x2="125" y2="0" stroke="#d4af37" stroke-width="3"/>

    <!-- Central Precision Diamond Glyph (Isometric Answer Prism) -->
    <path d="M 0,-85 L 75,-40 L 75,45 L 0,90 L -75,45 L -75,-40 Z" 
          stroke="#f4f4f5" stroke-width="4" fill="none"/>
    
    <!-- Facet Inner Lines -->
    <line x1="0" y1="0" x2="0" y2="90" stroke="url(#goldGrad)" stroke-width="3"/>
    <line x1="0" y1="0" x2="75" y2="-40" stroke="url(#goldGrad)" stroke-width="3"/>
    <line x1="0" y1="0" x2="-75" y2="-40" stroke="url(#goldGrad)" stroke-width="3"/>

    <!-- Core Citation Node -->
    <circle cx="0" cy="0" r="8" fill="#fef08a"/>
  </g>

  <!-- Typography -->
  <text x="400" y="595" text-anchor="middle" font-family="'Cinzel', 'Trajan Pro', -apple-system, BlinkMacSystemFont, 'Inter', serif" 
        font-size="40" font-weight="700" letter-spacing="9" fill="#f4f4f5">
    ANSW<tspan fill="#d4af37">RANK</tspan>
  </text>
  
  <text x="400" y="640" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif" 
        font-size="12" font-weight="500" letter-spacing="6" fill="#71717a">
    GENERATIVE ENGINE AUTHORITY
  </text>
</svg>
"""

# Logo 4: The Developer Brutalist (Bracket & Ascending Vector)
# Reminiscent of Linear, Vercel, Supabase. International Orange & Pure White on Matte Jet Black
svg_4 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <linearGradient id="bg4" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a0a0c"/>
      <stop offset="100%" stop-color="#121216"/>
    </linearGradient>
    <linearGradient id="orangeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ff6b00"/>
      <stop offset="100%" stop-color="#ff3b00"/>
    </linearGradient>
  </defs>

  <rect width="800" height="800" fill="url(#bg4)" rx="32"/>

  <!-- Icon: Monospaced Bracket [ Context ] + Rank Arrow ^ -->
  <g transform="translate(400, 330)">
    <!-- Left Square Bracket (LLM Context Boundary) -->
    <path d="M -60,-110 L -120,-110 L -120,110 L -60,110" 
          stroke="#ffffff" stroke-width="20" stroke-linecap="square" fill="none"/>

    <!-- Upward Sharp Ascending Rank Chevron (International Orange) -->
    <path d="M -30,50 L 30,-20 L 90,50" 
          stroke="url(#orangeGrad)" stroke-width="22" stroke-linecap="square" stroke-linejoin="miter" fill="none"/>
    
    <!-- Direct Citation Target Dot -->
    <circle cx="30" cy="-70" r="14" fill="#ff4f00"/>

    <!-- Right Climax Bracket -->
    <path d="M 80,-110 L 140,-110 L 140,110 L 80,110" 
          stroke="#27272a" stroke-width="14" stroke-linecap="square" fill="none"/>
  </g>

  <!-- Typography -->
  <text x="400" y="595" text-anchor="middle" font-family="'JetBrains Mono', 'Fira Code', -apple-system, BlinkMacSystemFont, monospace" 
        font-size="44" font-weight="800" letter-spacing="4" fill="#ffffff">
    answ<tspan fill="#ff4f00">_rank</tspan>
  </text>
  
  <text x="400" y="640" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif" 
        font-size="13" font-weight="600" letter-spacing="4" fill="#52525b">
    SYSTEMATIC AEO INFRASTRUCTURE
  </text>
</svg>
"""

# Logo 5: The Visibility Horizon (Radar Beacon & Focal Citation)
# Violet-Indigo, Pure White on Deep Carbon Slate
svg_5 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <linearGradient id="bg5" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a0a14"/>
      <stop offset="100%" stop-color="#121324"/>
    </linearGradient>
    <linearGradient id="violetGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#818cf8"/>
      <stop offset="100%" stop-color="#4f46e5"/>
    </linearGradient>
    <radialGradient id="beaconGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#a5b4fc" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#6366f1" stop-opacity="0.3"/>
      <stop offset="100%" stop-color="#1e1b4b" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="800" height="800" fill="url(#bg5)" rx="32"/>

  <!-- Icon: Radar Sweeps of Generative Retrieval with Focal Star -->
  <g transform="translate(400, 335)">
    <!-- Concentric radar range arcs -->
    <path d="M -140,40 A 150,150 0 0,1 140,40" stroke="#1e1b4b" stroke-width="4" fill="none"/>
    <path d="M -100,20 A 105,105 0 0,1 100,20" stroke="#312e81" stroke-width="3" fill="none"/>
    <path d="M -60,0 A 60,60 0 0,1 60,0" stroke="#4338ca" stroke-width="3" fill="none"/>

    <!-- Dynamic 45-degree beam angle (illuminating the citation) -->
    <polygon points="0,50 -90,-120 40,-150" fill="url(#beaconGlow)"/>

    <!-- Central Origin Point -->
    <circle cx="0" cy="50" r="10" fill="#4f46e5"/>
    
    <!-- Top-Tier Cited Brand Star (The Beacon) -->
    <g transform="translate(10, -110)">
      <polygon points="0,-25 7,-7 25,0 7,7 0,25 -7,7 -25,0 -7,-7" fill="#ffffff"/>
      <circle cx="0" cy="0" r="4" fill="#818cf8"/>
    </g>
  </g>

  <!-- Typography -->
  <text x="400" y="600" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Inter', 'SF Pro Display', sans-serif" 
        font-size="42" font-weight="700" letter-spacing="7" fill="#f8fafc">
    ANSW<tspan fill="#818cf8">RANK</tspan>
  </text>
  
  <text x="400" y="645" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif" 
        font-size="13" font-weight="600" letter-spacing="5" fill="#475569">
    GENERATIVE ENGINE VISIBILITY
  </text>
</svg>
"""

logos = [
    ("logo_1_citation_monogram", svg_1),
    ("logo_2_semantic_spectrum", svg_2),
    ("logo_3_ground_truth", svg_3),
    ("logo_4_bracket_chevron", svg_4),
    ("logo_5_visibility_beacon", svg_5),
]

for name, svg_content in logos:
    svg_path = os.path.join(OUT_DIR, f"{name}.svg")
    png_path = os.path.join(OUT_DIR, f"{name}.png")
    artifact_png_path = os.path.join(ARTIFACT_DIR, f"{name}.png")

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content.strip())
    
    # Render 1024x1024 PNG using rsvg-convert
    cmd = ["rsvg-convert", "-w", "1024", "-h", "1024", svg_path, "-o", png_path]
    subprocess.run(cmd, check=True)
    
    # Copy to artifact folder for markdown presentation
    subprocess.run(["cp", png_path, artifact_png_path], check=True)
    print(f"Generated: {name}.svg and {name}.png")

print("All 5 logos successfully generated and rendered!")
