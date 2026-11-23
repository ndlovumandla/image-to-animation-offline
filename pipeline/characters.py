"""Rich character presets, banner color palettes, and environment presets for the Video Studio."""

from __future__ import annotations

from typing import Any

BANNER_PALETTES: list[dict[str, str]] = [
    {
        "id": "navy_teal",
        "label": "Corporate Navy & Teal (Clean)",
        "prompt": "solid flat deep navy blue top banner with uniform pure white uppercase lettering (every letter identical pure white)",
    },
    {
        "id": "charcoal_gold",
        "label": "Executive Charcoal & Warm Gold",
        "prompt": "solid flat dark charcoal top banner with uniform pure white uppercase lettering (every letter identical pure white)",
    },
    {
        "id": "emerald_slate",
        "label": "Emerald Green & Slate",
        "prompt": "solid flat forest emerald green top banner with uniform pure white uppercase lettering (every letter identical pure white)",
    },
    {
        "id": "royal_coral",
        "label": "Royal Blue & Soft Coral",
        "prompt": "solid flat royal blue top banner with uniform pure white uppercase lettering (every letter identical pure white)",
    },
    {
        "id": "terracotta_navy",
        "label": "Warm Terracotta & Navy",
        "prompt": "solid flat warm terracotta top banner with uniform pure white uppercase lettering (every letter identical pure white)",
    },
    {
        "id": "minimal_ink",
        "label": "Minimal Black Ink & Highlight Yellow",
        "prompt": "clean white top banner with bold black outline and uniform solid black uppercase lettering (every letter identical black)",
    },
    {
        "id": "auto",
        "label": "Auto (Cohesive Single-Color Banner)",
        "prompt": "solid flat dark navy top banner with uniform pure white uppercase lettering (every letter identical pure white)",
    },
]

ENVIRONMENTS: list[dict[str, str]] = [
    {
        "id": "auto",
        "label": "Smart AI Environment (Matches Script Automatically)",
        "style_suffix": "hand drawn colored marker and ink illustration style, crisp bold outlines, flat watercolour-like fills, clean editorial explainer look",
        "director_rule": (
            "Choose the most fitting illustrated setting for each beat based on the script context: "
            "e.g. a bright modern office space with desks/monitors/glass walls, an outdoor workplace/field/park setting, "
            "a training classroom/workshop, a factory/operations floor, a boardroom, or a clean white canvas when showing pure diagrams. "
            "Always keep the background clean, softly tinted, and uncluttered behind crisp foreground callouts, labelled diagrams, and characters."
        ),
    },
    {
        "id": "office",
        "label": "Modern Office Space",
        "style_suffix": "hand drawn colored marker and ink illustration style, bright modern office interior background, crisp bold outlines, flat watercolour-like fills",
        "director_rule": (
            "Set scenes inside a bright, clean illustrated modern office space (desks, laptops, glass meeting rooms, wall charts, coffee cups, plants) "
            "with crisp foreground visual callouts, floating labelled cards, checklists, and diagrams."
        ),
    },
    {
        "id": "outdoor",
        "label": "Outdoor / Field / Site Environment",
        "style_suffix": "hand drawn colored marker and ink illustration style, bright outdoor daylight environment background, crisp bold outlines, flat watercolour-like fills",
        "director_rule": (
            "Set scenes in a bright, clean illustrated outdoor environment matching the script (city sidewalk, campus, workplace site, park, or sunny courtyard) "
            "with crisp foreground visual callouts, labelled diagrams, and icons."
        ),
    },
    {
        "id": "classroom",
        "label": "Training Room / Workshop",
        "style_suffix": "hand drawn colored marker and ink illustration style, bright training workshop room background, crisp bold outlines, flat watercolour-like fills",
        "director_rule": (
            "Set scenes in an illustrated training room / workshop (flipchart, seminar tables, learners taking notes, notebooks, projector screen) "
            "with crisp foreground visual callouts, labelled pillars, and diagrams."
        ),
    },
    {
        "id": "whiteboard",
        "label": "Classic Pure Whiteboard",
        "style_suffix": "hand drawn colored marker sketch style, whiteboard-animation look, pure white background, bold outlines, flat watercolour-like fills",
        "director_rule": (
            "Set every scene on a clean pure white whiteboard background with crisp hand-drawn marker sketches, icons, characters, and labelled diagrams."
        ),
    },
    {
        "id": "mixed_editorial",
        "label": "Editorial Magazine Explainer",
        "style_suffix": "hand drawn editorial ink and flat watercolour illustration style, soft warm off-white backdrop with grounded scene vignettes, crisp bold outlines",
        "director_rule": (
            "Use rich editorial explainer vignettes combining grounded mini-environments (desks, screens, real-world props, people collaborating) "
            "with crisp labelled diagrams and flow arrows."
        ),
    },
]

CHARACTER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "thandi_facilitator",
        "name": "Thandi (Facilitator)",
        "race": "Black African",
        "gender": "Female",
        "age_group": "30s-40s",
        "role": "Facilitator / Trainer",
        "default_voice": "Fiona.wav",
        "visual_description": "confident Black South African woman in her 30s with neat braided updo, warm smile, wearing round glasses and a tailored teal blazer over a white shirt, holding a marker",
    },
    {
        "id": "sipho_safety",
        "name": "Sipho (Safety Officer)",
        "race": "Black African",
        "gender": "Male",
        "age_group": "30s-40s",
        "role": "Safety / HSE",
        "default_voice": "Adrian.wav",
        "visual_description": "friendly Black African man in his 30s with short fade haircut and neat beard, wearing a high-visibility safety vest over a navy polo shirt and holding a clipboard",
    },
    {
        "id": "lerato_exec",
        "name": "Lerato (Executive)",
        "race": "Black African",
        "gender": "Female",
        "age_group": "50s+",
        "role": "Executive / Manager",
        "default_voice": "Elena.wav",
        "visual_description": "distinguished Black African woman executive in her 50s with short natural silver-streaked hair, pearl studs, wearing a crisp navy suit jacket",
    },
    {
        "id": "kagiso_tech",
        "name": "Kagiso (Tech Engineer)",
        "race": "Black African",
        "gender": "Male",
        "age_group": "20s",
        "role": "Tech / Engineer",
        "default_voice": "Jordan.wav",
        "visual_description": "energetic young Black African software engineer in his mid-20s with stylish short locs, wearing a smart casual slate hoodie under a light jacket, carrying a laptop",
    },
    {
        "id": "naledi_healthcare",
        "name": "Dr. Naledi (Healthcare)",
        "race": "Black African",
        "gender": "Female",
        "age_group": "30s-40s",
        "role": "Healthcare",
        "default_voice": "Alice.wav",
        "visual_description": "warm Black African female doctor in her 30s with braided ponytail, wearing a crisp white medical coat over teal scrubs with a stethoscope",
    },
    {
        "id": "chloe_creative",
        "name": "Chloe (Designer / Educator)",
        "race": "Coloured / Mixed Heritage",
        "gender": "Female",
        "age_group": "20s",
        "role": "Creative / Educator",
        "default_voice": "Emily.wav",
        "visual_description": "approachable young Coloured South African woman in her 20s with curly dark brown hair in a half-up bun, wearing an olive cardigan over a cream blouse",
    },
    {
        "id": "devon_field",
        "name": "Devon (Field Technician)",
        "race": "Coloured / Mixed Heritage",
        "gender": "Male",
        "age_group": "30s-40s",
        "role": "Trades / Field",
        "default_voice": "Connor.wav",
        "visual_description": "friendly Coloured South African field technician in his 30s with wavy dark hair and light stubble, wearing a rugged denim work shirt with rolled sleeves and tool lanyard",
    },
    {
        "id": "priya_analyst",
        "name": "Priya (Business Analyst)",
        "race": "Indian / South Asian",
        "gender": "Female",
        "age_group": "30s-40s",
        "role": "Corporate / Analyst",
        "default_voice": "Abigail.wav",
        "visual_description": "sharp Indian woman in her 30s with shoulder-length dark hair, wearing a burgundy blazer and smart glasses, gesturing with a tablet",
    },
    {
        "id": "rajesh_director",
        "name": "Rajesh (Operations Manager)",
        "race": "Indian / South Asian",
        "gender": "Male",
        "age_group": "50s+",
        "role": "Executive / Manager",
        "default_voice": "Henry.wav",
        "visual_description": "experienced South Asian male manager in his 50s with salt-and-pepper hair and trimmed moustache, wearing a light blue button-down shirt and dark trousers",
    },
    {
        "id": "ananya_trainer",
        "name": "Ananya (Young Trainer)",
        "race": "Indian / South Asian",
        "gender": "Female",
        "age_group": "20s",
        "role": "Facilitator / Trainer",
        "default_voice": "Cora.wav",
        "visual_description": "cheerful young Indian woman trainer in her mid-20s with long dark hair tied back, wearing a mustard yellow collared top and holding flashcards",
    },
    {
        "id": "pieter_auditor",
        "name": "Pieter (Quality Auditor)",
        "race": "White / European",
        "gender": "Male",
        "age_group": "30s-40s",
        "role": "Corporate / Analyst",
        "default_voice": "Alexander.wav",
        "visual_description": "friendly White South African man in his 40s with neat short brown hair and glasses, wearing a collared charcoal polo shirt and holding a checklist",
    },
    {
        "id": "sarah_instructor",
        "name": "Sarah (Lead Instructor)",
        "race": "White / European",
        "gender": "Female",
        "age_group": "30s-40s",
        "role": "Facilitator / Trainer",
        "default_voice": "Olivia.wav",
        "visual_description": "warm White woman instructor in her 30s with blonde bob haircut, wearing a navy sweater over a white collared shirt, expressive welcoming posture",
    },
    {
        "id": "david_senior",
        "name": "David (Senior Mentor)",
        "race": "White / European",
        "gender": "Male",
        "age_group": "50s+",
        "role": "Executive / Manager",
        "default_voice": "Thomas.wav",
        "visual_description": "wise senior White male mentor in his late 50s with grey hair, neat beard, wearing a tweed blazer over a crisp light shirt",
    },
    {
        "id": "claire_nurse",
        "name": "Claire (Clinical Nurse)",
        "race": "White / European",
        "gender": "Female",
        "age_group": "20s",
        "role": "Healthcare",
        "default_voice": "Gianna.wav",
        "visual_description": "kind young White female nurse in her 20s with auburn hair in a neat bun, wearing royal blue medical scrubs and an ID badge",
    },
    {
        "id": "mei_engineer",
        "name": "Mei (Systems Architect)",
        "race": "East Asian",
        "gender": "Female",
        "age_group": "30s-40s",
        "role": "Tech / Engineer",
        "default_voice": "Jade.wav",
        "visual_description": "composed East Asian woman engineer in her 30s with straight black bob hair and thin-framed glasses, wearing a clean charcoal mock-neck top",
    },
    {
        "id": "kenji_product",
        "name": "Kenji (Product Lead)",
        "race": "East Asian",
        "gender": "Male",
        "age_group": "20s",
        "role": "Creative / Educator",
        "default_voice": "Eli.wav",
        "visual_description": "friendly young East Asian man in his late 20s with neat dark hair, wearing a sage green overshirt over a white tee, holding a sketchbook",
    },
    {
        "id": "sofia_coach",
        "name": "Sofia (Learning Coach)",
        "race": "Hispanic / Latino",
        "gender": "Female",
        "age_group": "30s-40s",
        "role": "Facilitator / Trainer",
        "default_voice": "Layla.wav",
        "visual_description": "expressive Latina woman coach in her 30s with wavy dark brown hair, wearing a warm coral blazer over a white top, gesturing enthusiastically",
    },
    {
        "id": "mateo_trades",
        "name": "Mateo (Site Supervisor)",
        "race": "Hispanic / Latino",
        "gender": "Male",
        "age_group": "30s-40s",
        "role": "Safety / HSE",
        "default_voice": "Gabriel.wav",
        "visual_description": "reliable Latino site supervisor in his 40s wearing a white hard hat tucked under his arm, safety vest over a grey work shirt, warm confident expression",
    },
    {
        "id": "amira_strategist",
        "name": "Amira (Compliance Lead)",
        "race": "Middle Eastern",
        "gender": "Female",
        "age_group": "30s-40s",
        "role": "Corporate / Analyst",
        "default_voice": "Taylor.wav",
        "visual_description": "poised Middle Eastern woman in her 30s wearing a neat navy hijab and tailored cream blazer, holding a folder with documents",
    },
    {
        "id": "tariq_architect",
        "name": "Tariq (Operations Lead)",
        "race": "Middle Eastern",
        "gender": "Male",
        "age_group": "30s-40s",
        "role": "Tech / Engineer",
        "default_voice": "Michael.wav",
        "visual_description": "professional Middle Eastern man in his 30s with neatly trimmed beard, wearing a crisp white rolled-sleeve dress shirt and dark chinos",
    },
    {
        "id": "sam_educator",
        "name": "Sam (Workshop Host)",
        "race": "Coloured / Mixed Heritage",
        "gender": "Non-binary",
        "age_group": "20s",
        "role": "Creative / Educator",
        "default_voice": "Jordan.wav",
        "visual_description": "friendly non-binary facilitator in their late 20s with short curly dark hair and stylish rectangular glasses, wearing a teal button-up shirt over a white tee",
    },
    {
        "id": "alex_consultant",
        "name": "Alex (Workplace Consultant)",
        "race": "White / European",
        "gender": "Non-binary",
        "age_group": "30s-40s",
        "role": "Corporate / Analyst",
        "default_voice": "Ryan.wav",
        "visual_description": "approachable non-binary workplace consultant in their 30s with cropped wavy brown hair, wearing a structured slate blazer and minimalist watch",
    },
    {
        "id": "zinhle_learner",
        "name": "Zinhle (Apprentice / Learner)",
        "race": "Black African",
        "gender": "Female",
        "age_group": "20s",
        "role": "Trades / Field",
        "default_voice": "Fiona.wav",
        "visual_description": "curious young Black African learner in her early 20s with box braids, wearing a bright royal blue polo shirt and carrying a notebook and pen",
    },
    {
        "id": "liam_student",
        "name": "Liam (Graduate Trainee)",
        "race": "White / European",
        "gender": "Male",
        "age_group": "20s",
        "role": "Tech / Engineer",
        "default_voice": "Miles.wav",
        "visual_description": "enthusiastic young White male graduate trainee in his early 20s with messy brown hair, wearing a navy crew-neck sweater and backpack strap",
    },
]


def get_palette(palette_id: str) -> dict[str, str]:
    for p in BANNER_PALETTES:
        if p["id"] == palette_id:
            return p
    return BANNER_PALETTES[0]


def get_environment(env_id: str) -> dict[str, str]:
    for e in ENVIRONMENTS:
        if e["id"] == env_id:
            return e
    return ENVIRONMENTS[0]


def filter_characters(
    race: str = "",
    gender: str = "",
    age_group: str = "",
    role: str = "",
    search: str = "",
) -> list[dict[str, Any]]:
    results = []
    q = search.strip().lower()
    for ch in CHARACTER_PRESETS:
        if race and ch["race"].lower() != race.lower():
            continue
        if gender and ch["gender"].lower() != gender.lower():
            continue
        if age_group and ch["age_group"].lower() != age_group.lower():
            continue
        if role and ch["role"].lower() != role.lower():
            continue
        if q:
            hay = " ".join([
                ch["name"], ch["race"], ch["gender"], ch["age_group"],
                ch["role"], ch["visual_description"], ch["default_voice"],
            ]).lower()
            if q not in hay:
                continue
        results.append(ch)
    return results
