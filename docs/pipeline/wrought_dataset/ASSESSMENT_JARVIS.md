# Jarvis's assessment of the night run

Read by `gemma4:12b` (the stack's vision role) against the teacher plate, PICK.md and the 002 same-game test, frame by frame; write-ups by the same model from its own verdicts. The reason role was not used: stack.toml binds it to the node's card, which was rendering the night run. Independent of Claude's read -- no gate verdicts or metrics were shown.

**187 of 840 frames kept so far.**

Based on the provided dataset, here is the summary of the evaluation results for the items provided:

### **Summary Statistics**
*   **Total Samples:** 29
*   **Accepted (Keep):** 3
*   **Rejected:** 26
*   **Success Rate:** ~10.3%

### **Performance Breakdown by Category**

| Category | Count | Success Rate | Primary Reasons for Failure |
| :--- | :--- | :--- | :--- |
| **Style: Wrought** | 5 | 60% | Most failures in this category were due to "Painterly" or "CGI" influences. |
| **Style: CGI** | 11 | 0% | Failed consistently due to being too "clean," "polished," or "digital." |
| **Style: Painterly** | 10 | 0% | Failed due to being too "soft," "illustrative," or "muted." |
| **Style: Photo** | 3 | 0% | Failed due to "pore-photos," "photorealism," or "cosplay" looks. |

### **Key Evaluation Criteria Analysis**

1.  **Style Consistency ("Wrought"):** This was the most critical failure point. The majority of candidates were rejected for being **"Painterly"** (too artistic/soft) or **"CGI"** (too polished/clean). The "Wrought" requirement demands high material density, gritty textures (metal/leather), and "hard key" lighting.
2.  **Race/Character Requirements (Kemonomimi):** There were specific failures where the candidate featured a full animal head/muzzle instead of a human face with animal features. (e.g., IDs 073, 098).
3.  **Material Density:** A recurring note for rejected items (

Based on the provided data, the evaluation for the items from **067 to 099** follows a very consistent pattern regarding why these candidates were rejected. 

### **Summary of Rejection Criteria:**

1.  **"Wrought" vs. "CGI/Photo" Style:**
    The primary reason for rejection across almost all entries (e.g., 068, 070, 073, 079, 082, 090, 091, 093) is that the candidates look like **"CGI catalog"** or **"photo-realistic"** assets. The "teacher's" style is specifically defined as **"wrought,"** which implies a tactile, hand-sculpted, and gritty aesthetic rather than a polished, modern 3D render or a high-fidelity "pore-photo" skin.

2.  **Material Density and Grit:**
    Many candidates (e.g., 071, 073, 088, 090, 091) were rejected because their **metal and leather textures** lacked the "edge wear," "grit," and "heavy density" of the target style. They were described as having "smooth shaders" or "light textures" rather than the rugged, heavy materials required.

3.  **Color Palette:**
    A recurring failure (e.g., 070, 071, 076, 082, 083, 094, 097) is that the palettes are consistently described as **"muted," "desaturated," "washed out,"** or **"too blue/cool."** The target style prefers "earth/iron tones" and "high-contrast" elements.

4.  **Lighting:**

Based on the evaluation data provided, here is the analysis of the candidates:

### **Successful Candidates (Keep: True)**
These candidates perfectly matched the "wrought" style, featuring high material density, correct leather/metal wear, and appropriate facial structures.
*   **065**: (Score: 9) Matches aesthetic density and material realism perfectly.
*   **071**: (Score: 9) Strong match on texture density and facial structure.
*   **075**: (Score: 9) High quality leather grain and metal wear; clear face.
*   **079**: (Score: 9) Captures correct textures and anatomy.
*   **082**: (Score: 10) Perfect match on texture, lighting, and proportions.
*   **083**: (Score: 10) Perfect execution on wrought aesthetic and dragonborn features.
*   **093**: (Score: 9) Strong adherence to style; proportions align perfectly.
*   **096**: (Score: 10) Perfect adherence to density, lighting, and physical markers.

### **Failed Candidates (Keep: False)**
The majority of these failed due to three primary reasons:

**1. Incorrect Style ("CGI" or "Photo")**
Many candidates were rejected because they looked like modern, high-fidelity 3D game assets or photorealistic renders rather than "wrought" artistic studies.
*   **Examples:** 067, 069, 072, 073, 074, 076, 081, 084, 085, 086, 087, 089, 095, 097, 098, 099.
*

The data identifies a clear pattern regarding the "wrought" style and "race_reads" criteria. The core reason for the high volume of "keep: false" results is the failure to distinguish between a **photorealistic human** and a **stylized fantasy character (Orc/Beast-folk)**.

### Analysis of Rejection Reasons:

**1. The "Wrought" Style Constraint (Most Common Failure)**
The "wrought" style is defined by material density—specifically metal, leather, and heavy textures. 
*   **Why they failed:** Most candidates (e.g., 066, 071, 073, 094) were rejected because their skins were "pore-photos" or "high-fidelity renders." If the skin looks like real human skin with visible pores, it is rejected in favor of a "sculpted" or "painted" look.
*   **The "CGI/Photo" Trap:** Candidates like 069 (cgi) and 093 (painterly) were rejected because, while not "photographs," they lacked the specific, gritty, metallic/leather-heavy texture density that defines "wrought."

**2. Race_Read (Orc/Beast-folk Requirement)**
The prompt requires a non-human fantasy race.
*   **The "Human" Problem:** A significant number of candidates (068, 076, 082, 090) were rejected because they appeared as standard humans. Even if the art style was high-quality, the lack of defining features (tusks, green skin, horns, or beast-like features) resulted in a failure of the "race_read" check.
*   **The "Face" vs. "Mask" Distinction:** Note 083 is a rare success where the face is described as a "

Based on the provided data, here is the analysis of the candidates:

### **Summary Statistics**
*   **Total Candidates Evaluated:** 40
*   **Total "Keep" (Pass):** 14
*   **Total "Fail" (Discard):** 26
*   **Success Rate:** 35%

### **Key Performance Indicators**
*   **Highest Scores:** 10 (Candidates 073 and 092)
*   **Average Score of Kept Candidates:** ~9.3
*   **Average Score of Failed Candidates:** ~3.8

### **Failure Analysis (Why candidates were rejected):**
The primary reasons for rejection can be categorized into three main "Style" failures:

1.  **"Photo-Realism" Trap (The most common failure):**
    *   Candidates (064, 068, 069, 070, 072, 081, 089, 095) were rejected because the skin textures were identified as "pore-photos" or "digital scans." The requirement is for a "wrought" look—which implies hand-crafted, high-fidelity game assets—rather than hyper-realistic human photography.
2.  **"Painterly/Soft" Aesthetics:**
    *   Candidates (065, 079, 080, 087, 093, 094, 096) were rejected for being too soft, illustrative, or "painterly." These failed to capture the "grit," "edge-wear," and "material density" of the target style.
3.  **"CGI/Catalog" Polish:**
    *   Candidates (063, 067, 071, 08

Based on the provided data, here is the analysis of the candidates:

### **Summary of Evaluation**
The primary criteria for a "Keep" (score of 9) were:
1.  **Style:** Must be "wrought" (grit-heavy, tactile materials, high-contrast lighting).
2.  **Race:** Must be "Orc" or "Kemonomimi" (avoiding "human/elf" defaults).
3.  **Material Density:** Metal and leather must have "wear/grain," not look like smooth digital assets or "pore-photos."
4.  **Consistency:** The character must look like it belongs in the specific "teacher" universe.

### **Accepted Candidates (Keep: True)**
The following candidates successfully met all criteria, specifically capturing the "wrought" aesthetic, correct racial features, and high material density:
*   **066:** Excellent translation of assets into an elf-variant; matches perfectly.
*   **080:** Strong adherence to material weight and lighting.
*   **084:** Matches wrought texture, lighting profile, and accurate proportions.
*   **090:** Matches material density and lighting while maintaining a grounded face.
*   **092:** Matches technical requirements (lighting, materials, and facial structure).
*   **096:** Captures the heavy metal and leather grain perfectly.

### **Rejected Candidates (Keep: False)**
The reasons for rejection generally fall into three categories:

**1. Style Failures (The most common issue):**
Many candidates (067, 068, 069, 070, 071, 073, 074, 075, 077, 078, 081, 086, 088, 08

### human

The majority of this batch failed because the model is defaulting to "photorealism" instead of the "wrought" aesthetic. We are getting human girls in high-fidelity skin textures (pore-photos) instead of the dense, stylized game-asset look defined in the PICK.md.

**What’s working:**
The model successfully identified the "female" and "fit" attributes across the board, but it failed the core creative pillars of the set.

**Systematic Failures:**
The primary issue is a **Style/Race Drift**. The model is ignoring the "wrought" instruction and substituting "photorealistic human" as the default.
*   **Race Failure:** Almost every frame (000, 003, 005, 009, 016, 023, 030, etc.) produced a human face instead of an orc/beast-folk.
*   **Material/Style Failure:** The "wrought" requirement is being ignored in favor of "standard CGI" or "photoreal" textures. Frames 002, 011, and 019 show "clean" renders that lack the grit, metal edge-wear, and leather grain required.
*   **Lighting/Color Failures:** Frames 010, 012, and 013 show soft/ambient lighting instead of the hard key lighting required by the teacher.

**Keep for LoRA:**
*   **025:** This is the only frame that hit the mark—correct race, wrought texture, and material density.

**Adjustments:**
1.  **Prompt:** We need to significantly penalize "photorealistic," "skin pores," and "human" in the negative prompt. We need to double down on "wrought," "heavy metal wear," and "stylized game

Based on the provided data, here is the summary of the results:

**Summary Statistics:**
*   **Total evaluated:** 40
*   **Total kept:** 18
*   **Total failed:** 22
*   **Average Score (Keep):** 9.67
*   **Average Score (Fail):** 4.36

**Key Performance Insights:**
1.  **Style Consistency:** The "wrought" style was the primary differentiator. Candidates labeled as "painterly," "photo," or "cgi" consistently failed, primarily due to skin textures being too "soft" or "pore-heavy" (photorealistic) rather than having the "grit" and "material density" required.
2.  **Material Density:** High-scoring images (Score 9-10) were specifically noted for their "metal and leather density" and "tangible" textures.
3.  **Common Failure Points:**
    *   **Skin Texture:** Many failed because the skin looked like a "3D scan" or "pore-photo" rather than a hand-crafted game asset.
    *   **Lighting:** "Soft/ambient" lighting caused failures; the preferred style requires "hard" lighting and "texture density."
    *   **Age/Race Consistency:** Candidates that failed the age requirement (e.g., #069, #074, #099) or the race requirement (e.g., #071, #085) were automatically disqualified.

**Selected "Keep" Index List:**
060, 061, 062, 065, 068, 072, 075, 076, 077, 078, 080, 081, 082,

To determine the correct candidates, I evaluated each entry against the core requirements: **"Wrought" style** (heavy material density, metallic/leather wear, hard key lighting), **Race** (Beast-folk/Orc features, not human), and **Skin Texture** (Sculpted/game-asset style, not "pore-photos" or photorealistic skin).

Here are the candidates that passed:

*   **064**: (Keep: true) Strong match on material density and face type; skin is sculpted rather than photorealistic.
*   **072**: (Keep: true) Solid execution on the wrought textures and race markers; fits the world perfectly.
*   **076**: (Keep: true) Strong adherence to the wrought style; textures are sharp and the face carries the correct age and race markers.
*   **083**: (Keep: true) Strong match; hits all textural requirements and maintains the intended proportions and aesthetic.
*   **084**: (Keep: true) Solid translation of the teacher's aesthetic; materials and lighting are consistent with the required style.
*   **086**: (Keep: true) Candidate perfectly matches the studio lighting, material density, and fantasy-realism aesthetic of the teacher.
*   **095**: (Keep: true) Solid pass; the leather and metal textures match the teacher's density and the face is a believable person.
*   **096**: (Keep: true) High quality execution; she fits the world perfectly without the visual artifacts of common 3D renders.

**Summary of Rejections:**
*   **Style Mismatch:** Items 065, 066, 067, 068, 069, 070, 071, 073, 074,
