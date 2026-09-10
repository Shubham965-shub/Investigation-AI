"""Reviewed product-name standardization mapping for Action Center's Product
column (2026-09-10, per the user).

The Open Investigations table's Product column showed 152 distinct raw
strings for what turned out to be ~96 real products — the same drug/strength
entered under wildly different conventions across dim_product.name_of_material
(raw SAP-style material codes alongside human-readable names) and this app's
own title-extraction fallback (_extract_product_from_title in
routers/action_center.py). Reviewed and approved by the user against a
full clustering + confidence-tier writeup (every merge only joins the same
drug at the same strength/form — nothing merged across strengths).

STATUS: approved, NOT YET WIRED into _resolve_product()/the summary endpoint
— kept here for reference until that wiring is done. When it is: look up the
raw product string in PRODUCT_NAME_CANONICAL and use the mapped value if
present, otherwise fall back to the raw string unchanged.

One exception already flagged as a real bug, not a naming variant: the
Famotidine 40mg/5mL entries include two raw strings with a stability-test
condition ("N25°C/ 60%RH" / "N30°C/ 75%RH") wrongly baked into the product
name by _extract_product_from_title's own regex — that should be fixed in
the extraction regex directly, not just papered over by this mapping.
"""
from __future__ import annotations

PRODUCT_NAME_CANONICAL: dict[str, str] = {
    "Alfa0.25mcgSGCZODORAY0.25mcg30sHDPESPSAS": "Alfacalcidol Capsules 0.25mcg (SGC)",
    "Alfacalcidol Capsules 0.25mcg (SGC)": "Alfacalcidol Capsules 0.25mcg (SGC)",
    "Alfacalcidol Capsules [0.25mcg] [SGC][CANADA]": "Alfacalcidol Capsules 0.25mcg (SGC)",
    "Alfacalcidol Capsules [0.25mcg][SGC]": "Alfacalcidol Capsules 0.25mcg (SGC)",
    "Alfacalcidol Capsules-0.25mcg-SGC-CANADA": "Alfacalcidol Capsules 0.25mcg (SGC)",
    "AlfacalcidolCap0.25MCG-SGC-30s-SPUK": "Alfacalcidol Capsules 0.25mcg (SGC)",
    # Different strength from the 0.25mcg/1mcg groups — kept separate.
    "Alfacalcidol Capsules [0.5mcg][SGC]": "Alfacalcidol Capsules 0.5mcg (SGC)",
    # Different strength — kept separate.
    "Alfacalcidol Capsules [1mcg]": "Alfacalcidol Capsules 1mcg",
    "Alfacalcidol Capsules [1mcg] [SGC][CANADA]": "Alfacalcidol Capsules 1mcg",
    # Only one variant seen — no merge needed, formatting only.
    "Amlo&ChlorthalidoneTabs 5/12.5mg30sUS-EX": "Amlodipine & Chlorthalidone 5/12.5mg",
    "Arte/Lume tab-20/120mg Dispersible Tab": "Arte/Lume Dispersible Tablets 20/120mg",
    # Source title itself is truncated (cuts off mid-word) — separate data-quality issue, not a naming variant.
    "Artesunate Rectal Capsules [100mg] [Soft gel": "Artesunate Rectal Capsules 100mg (Soft Gel)",
    "Baclofen Tablets BP [10mg]": "Baclofen Tablets BP 10mg",
    "Betadexamine 2 mg Tablets": "Betadexamine 2mg Tablets",
    # Bulk/blend manufacturing stage, not a finished dose — kept distinct from finished Ibuprofen products below.
    "Blend for Ibuprofen tabs [400/600/800mg]": "Blend for Ibuprofen Tablets 400/600/800mg",
    # Bulk/blend stage — kept distinct from finished Pramipexole products below.
    "Blend for Pramipexole Di-HCl Tablets": "Blend for Pramipexole Di-HCl Tablets",
    "BuspironeHCl tab USP15mg-180s-Strides-US": "Buspirone HCl Tablets USP 15mg",
    # High confidence — same drug, same strength, same soft-gelatin capsule form throughout.
    "Calcitriol 0.25mcg capsules": "Calcitriol Capsules 0.25mcg (SGC)",
    "Calcitriol Caps 0.25mcg-SGC-US": "Calcitriol Capsules 0.25mcg (SGC)",
    "Calcitriol Caps 0.25mcg-SGC-US-EX": "Calcitriol Capsules 0.25mcg (SGC)",
    "Calcitriol Capsules 0.25 mcg": "Calcitriol Capsules 0.25mcg (SGC)",
    "Calcitriol Capsules 0.25mcg": "Calcitriol Capsules 0.25mcg (SGC)",
    "Calcitriol Capsules 0.25mcg (SGC)": "Calcitriol Capsules 0.25mcg (SGC)",
    "Calcitriol Capsules [0.25mcg] [Soft Gelatin] [US]": "Calcitriol Capsules 0.25mcg (SGC)",
    "Calcitriolcaps0.25mcg,SG,100's,PS-Canada": "Calcitriol Capsules 0.25mcg (SGC)",
    # Different strength — kept separate.
    "Calcitriol Capsules 0.5 mcg": "Calcitriol Capsules 0.5mcg",
    # 500mcg = 0.5mg — same strength, different unit.
    "Colchicine Tablets 0.5mg": "Colchicine Tablets 0.5mg",
    "Colchicine tablets 500 mcg (UK)": "Colchicine Tablets 0.5mg",
    # Different strength from the 800 IU entry — kept separate.
    "Colecalciferol 3200 IU Capsules-SG": "Colecalciferol 3200 IU Capsules (Soft Gel)",
    # Different strength — kept separate.
    "Colecalciferol 800 IU Capsules-SG": "Colecalciferol 800 IU Capsules (Soft Gel)",
    "Cortisone Tab 5mg-Cortate 5-Aspen-Aus": "Cortisone Tablets 5mg (Cortate, Aspen)",
    "Cyclosporine 100 mg capsules": "Cyclosporine Capsules USP 100mg",
    "Cyclosporine Capsules USP 100mg": "Cyclosporine Capsules USP 100mg",
    # Different strength from 25/50/100mg — kept separate.
    "Cyclosporine Caps USP modified 10mg-SG": "Cyclosporine Capsules USP 10mg (modified)",
    # Different strength — kept separate from 10/50/100mg.
    "Cyclosporine Capsules USP 25 mg (modified) [SGC]": "Cyclosporine Capsules USP 25mg (modified)",
    "Cyclosporine Capsules USP 25mg": "Cyclosporine Capsules USP 25mg (modified)",
    # "SGja" entry is a truncated title (cuts off mid-word).
    "Cyclosporine Capsules USP 50 mg (modified) [SGja": "Cyclosporine Capsules USP 50mg (modified)",
    "Cyclosporine Capsules USP 50mg [SGC]": "Cyclosporine Capsules USP 50mg (modified)",
    "Dolutegravir Sodium [Desano]-IH": "Dolutegravir Sodium (Desano)",
    "Doxycycline Hyclate Tablets 50mg": "Doxycycline Hyclate Tablets 50mg",
    # Same strength/form throughout — high confidence.
    "Dutasteride 0.5mg [SGC]- 6OB": "Dutasteride Capsules 0.5mg (SGC)",
    "Dutasteride Capsules [0.5mg] [SGC]": "Dutasteride Capsules 0.5mg (SGC)",
    "Dutasteride Capsules [0.5mg] [Soft Gelatin]": "Dutasteride Capsules 0.5mg (SGC)",
    "DutasterideCap,0.5mgSG,3x10sPOSVITEL-MX": "Dutasteride Capsules 0.5mg (SGC)",
    "Extended Phenytoin Sod Cap USP-100mg--EX": "Extended Phenytoin Sodium Capsules USP 100mg",
    # BUG, not just a naming variant: the last two entries have a stability-test condition ("N25°C/60%RH") wrongly baked into the product name by my own title-extraction fallback — recommend fixing the extraction regex to strip this, not just mapping it here.
    "Famotidine for OS 40mg/5mL": "Famotidine for Oral Suspension USP 40mg/5mL",
    "Famotidine oral suspension 40mG/5ML": "Famotidine for Oral Suspension USP 40mg/5mL",
    "N25°C/ 60%RH Famotidine for ORS USP 40 mg/5 mL": "Famotidine for Oral Suspension USP 40mg/5mL",
    "N30°C/ 75%RH Famotidine for ORS USP 40 mg/5 mL": "Famotidine for Oral Suspension USP 40mg/5mL",
    # Same substance, different pharmacopeia naming — high confidence.
    "Glycerin USP": "Glycerin / Glycerol USP/BP",
    "Glycerol BP-PhEur / Glycerin USP/IP": "Glycerin / Glycerol USP/BP",
    "Glycopyrronium Br 1mg/5ml OS1s150ml-SPUK": "Glycopyrronium Bromide 1mg/5mL Oral Solution",
    "Hydralazine HCl Tab 50mg-100s-Strides-US": "Hydralazine HCl Tablets 50mg",
    # No strength or form given in source — left unmerged rather than guessed.
    "Ibuprofen": "Ibuprofen (strength/form not specified)",
    "Ibuprofen Caps 200mg-SGC-US": "Ibuprofen Capsules 200mg (SGC)",
    "Ibuprofen Capsules 200mg [SGC][Minis]": "Ibuprofen Capsules 200mg (SGC)",
    "Ibuprofen Capsules [200mg][SGC]": "Ibuprofen Capsules 200mg (SGC)",
    # No strength given — not assumed to be the 100mg/5mL entry below.
    "Ibuprofen Oral Suspension": "Ibuprofen Oral Suspension (strength not specified)",
    "Ibuprofen Oral Suspension 100mg/5mL": "Ibuprofen Oral Suspension 100mg/5mL",
    # Different form/strength from the 200mg capsules — kept separate.
    "Ibuprofen Tablets USP 400mg": "Ibuprofen Tablets USP 400mg",
    "Icosapentethyl capsules 1g": "Icosapentethyl Capsules 1g",
    "Imipramine Hydrochloride Tablets": "Imipramine Hydrochloride Tablets",
    "Lamotrigine Tablets 100mg": "Lamotrigine Tablets 100mg",
    "Loperamide HCl Cap-2mg-HGC-Poland": "Loperamide HCl Capsules 2mg (HGC)",
    "MMF ORS 200mg/ml": "MMF (Mycophenolate Mofetil) for Oral Suspension USP 200mg/mL",
    "MMF ORS USP 200mg/ml": "MMF (Mycophenolate Mofetil) for Oral Suspension USP 200mg/mL",
    # Different Macrogol formulation (no electrolytes) — kept separate from Macrogol Plus Electrolytes below.
    "Macrogol 4000[10g] [Sachets]POS": "Macrogol 4000 10g Sachets",
    # 13.7/13.71/13.72g treated as the same standard sachet dose across markets/brands (EU, STADA, Macrovic). Medium confidence on the 2 entries lacking an explicit gram figure (grouped by "Plus Electrolyt(es)" naming).
    "Macrogol Elektrolyte 13,7 g/Powder": "Macrogol Plus Electrolytes ~13.7g",
    "Macrogol Natural [13.71g] [Sachets]": "Macrogol Plus Electrolytes ~13.7g",
    "Macrogol Plus Electrolyt [Pow for OS] EU": "Macrogol Plus Electrolytes ~13.7g",
    "Macrogol Plus Electrolytes 13.72g": "Macrogol Plus Electrolytes ~13.7g",
    "Macrogol Plus Electrolytes [13.72g]": "Macrogol Plus Electrolytes ~13.7g",
    "Macrogol Plus Electrolytes [Macrovic]": "Macrogol Plus Electrolytes ~13.7g",
    "Macrogol Plus Electrolytes-13.71g-pf OS": "Macrogol Plus Electrolytes ~13.7g",
    "Macrogol+Electrolytes-13.72g-pf OS-STADA": "Macrogol Plus Electrolytes ~13.7g",
    # 6.86g is exactly half of 13.72g — likely a distinct half-sachet SKU, kept separate rather than merged.
    "Macrogol+electrPOS,6.86g20sPholi-HS-TPSA": "Macrogol Plus Electrolytes 6.86g (half-sachet)",
    # Different form from the oral solution below — kept separate.
    "Magnesium Sulfate USP(dried granular)": "Magnesium Sulfate USP (dried granular)",
    # Kept separate from the dried granular raw-material entry above.
    "Magnesium sulfate oral solution": "Magnesium Sulfate Oral Solution",
    "Mycophenolat Mofeti cap 250mg-HGC-US-ALT": "Mycophenolate Mofetil Capsules USP 250mg (Hard Gelatin)",
    "Mycophenolate Mofetil Capsules USP [250 mg] [Hard Gelatin] [US]": "Mycophenolate Mofetil Capsules USP 250mg (Hard Gelatin)",
    # Different form/strength from the 250mg capsule — kept separate.
    "Mycophenolat Mofetil tab 500mg-FC-US-ALT": "Mycophenolate Mofetil Tablets 500mg",
    "Mycophenolate Tab 500mg-500s-Strides-Inc": "Mycophenolate Mofetil Tablets 500mg",
    # Different form — kept separate from the capsule/tablet entries.
    "Mycophenolate Mofetil for OS USP200mg/ml": "Mycophenolate Mofetil for Oral Suspension USP 200mg/mL",
    # Genuine "no product" cases (mostly Deviation-type events with no product reference at all) — out of scope for this cleanup, nothing to standardize.
    "Not Applicable": "Not Applicable",
    "Omega3 Acid Ethyl Ester 90-EP/USP-DM": "Omega-3 Acid Ethyl Ester 90 EP/USP",
    "Oseltamivir Phosphate cap 75mg-HG-US-DMF": "Oseltamivir Phosphate Capsules 75mg (HG)",
    "Oxybutynin Chloride Tablets USP 5mg": "Oxybutynin Chloride Tablets USP 5mg",
    # Medium confidence — "Panafcortelone" is Aspen's brand name for Prednisolone; both entries are explicitly Aspen 25mg.
    "PANAFCORTELONE TAB-25MG-30-ASPENAUS": "Prednisolone Tablets 25mg (Aspen / Panafcortelone)",
    "Prednisolone Tab 25mg - Aspen": "Prednisolone Tablets 25mg (Aspen / Panafcortelone)",
    # Medium confidence on bare "PEG 3350" (no gram figure) — grouped here since it's the most common PEG 3350 dose seen.
    "PEG 3350": "PEG 3350 Powder for Solution 17g",
    "PEG 3350, Powder for Solution 17g": "PEG 3350 Powder for Solution 17g",
    "PL-PEG-17G-PIONEER LIFE SCIENCES-US": "PEG 3350 Powder for Solution 17g",
    # Different pack size/strength — kept separate from the 17g group.
    "PEG 3350 powder for solution 510g (Hydralax)": "PEG 3350 Powder for Solution 510g (Hydralax)",
    # "Bot" = bottle packaging suffix — same formulation otherwise. Kept as its own group since the electrolyte composition differs from the 17g/510g powder entries.
    "PEG3350 OS 178.7/7.3/1.12/0.9/0.5g": "PEG 3350 Oral Solution 178.7/7.3/1.12/0.9/0.5g",
    "PEG3350 OS 178.7/7.3/1.12/0.9/0.5g Bot": "PEG 3350 Oral Solution 178.7/7.3/1.12/0.9/0.5g",
    "Polyoxyl 40 Castor Oil USNF/BP/Ph.Eur/IP": "Polyoxyl 40 Castor Oil USNF/BP/Ph.Eur/IP",
    # Different strength from the 0.125mg/0.25mg entries — kept separate.
    "Pramipexole DiHCl Tab 1.5mg-90-SPI-US": "Pramipexole Dihydrochloride Tablets 1.5mg",
    # Different strength — kept separate.
    "Pramipexole Dihydrochloride Tab 0.125mg": "Pramipexole Dihydrochloride Tablets 0.125mg",
    # Different strength — kept separate.
    "Pramipexole Dihydrochloride Tab 0.25mg": "Pramipexole Dihydrochloride Tablets 0.25mg",
    # Raw-material grade — kept separate from the finished 25mg tablet.
    "Prednisolone BP/PhEur-Micronized": "Prednisolone BP/PhEur (Micronized)",
    # "Panafcort" is Aspen's brand name for Prednisone — both entries explicitly Aspen 1mg.
    "Prednisone Tab 1mg - Aspen": "Prednisone Tablets 1mg (Aspen / Panafcort)",
    "Prednisone Tablets 1mg (PANAFCORT)": "Prednisone Tablets 1mg (Aspen / Panafcort)",
    # Different strength — kept separate.
    "Prednisone tablets USP 5mg-US": "Prednisone Tablets USP 5mg",
    # Different strength — kept separate.
    "Prednisone tablets USP10mg-1000'sSPI US": "Prednisone Tablets USP 10mg",
    # Different strength — kept separate.
    "Prednisone tablets USP20mg-1000's-USSPI": "Prednisone Tablets USP 20mg",
    "Promethazine Hydrochloride 25mg Tablets": "Promethazine Hydrochloride Tablets 25mg",
    "Propyl Gallate BP/Ph.Eur.-SHRI VINAYAK C": "Propyl Gallate BP/Ph.Eur.",
    "Quinine Sulfate tab 200mg-2x14's-SPUK": "Quinine Sulfate Tablets 200mg",
    "Quinine Sulfate tab 200mg-Copharma": "Quinine Sulfate Tablets 200mg",
    # Different strength — kept separate.
    "Quinine sulfate tab BP 300mg-FC": "Quinine Sulfate Tablets BP 300mg",
    "Ranitidine tablets USP 300mg": "Ranitidine Tablets USP 300mg",
    # Flavored SKU — kept separate from the unflavored Strigol entry as a likely distinct product code.
    "STRIGOL ORANGE-30's-SPUK": "Strigol Orange (30s)",
    # Kept separate from the Orange-flavored SKU.
    "STRIGOL-30's-SPUK": "Strigol (30s)",
    # Middle entry is a spacing typo ("ORALSUSPENSION") of the first — high confidence merge.
    "SUCRALFATE ORAL SUSPENSION 1G/10ML[420ml]": "Sucralfate Oral Suspension 1g/10mL (420mL)",
    "SUCRALFATE ORALSUSPENSION 1G/10ML[420ml]": "Sucralfate Oral Suspension 1g/10mL (420mL)",
    "Sucralfate OSus 1g/10mL-420ml-bottle-US": "Sucralfate Oral Suspension 1g/10mL (420mL)",
    "Sevelamer Carbonate for Oral Suspension 2.4 g": "Sevelamer Carbonate for Oral Suspension 2.4g",
    # Same triple-salt concentrations across all three — high confidence.
    "Sod sulfate-OS 17.5/3.13/1.6g-6[177ml]EX": "Sodium/Potassium/Magnesium Sulfate Oral Solution 17.5g/3.13g/1.6g",
    "Sod-sulf,Pot-sulf,Mag-sulf OS-US-SPI 2`s": "Sodium/Potassium/Magnesium Sulfate Oral Solution 17.5g/3.13g/1.6g",
    "Sod/Pot/Mag/Sulfate Oral Solution (17.5 g/3.13 g/1.6 g)": "Sodium/Potassium/Magnesium Sulfate Oral Solution 17.5g/3.13g/1.6g",
    "Sorbitol Sorbitan Solution USNF-DM": "Sorbitol Sorbitan Solution USNF",
    # Different concentration from the 1g/10mL group — kept separate.
    "Sucralfate Oral Suspension 1g/ 5ml": "Sucralfate Oral Suspension 1g/5mL",
    # Raw-material grade — kept separate.
    "Sucralfate USP (Micronized)": "Sucralfate USP (Micronized)",
    # Pure casing difference — high confidence.
    "TDF Tablets 300mg": "TDF (Tenofovir Disoproxil Fumarate) Tablets 300mg",
    "TDF tablets 300mg": "TDF (Tenofovir Disoproxil Fumarate) Tablets 300mg",
    # Same strength/form across all 4 — high confidence.
    "Tacrolimus Cap USP 0.5mg-HGC-SA": "Tacrolimus Capsules USP 0.5mg (HGC)",
    "Tacrolimus Cap USP 0.5mg-HGC-US": "Tacrolimus Capsules USP 0.5mg (HGC)",
    "Tacrolimus Capsules 0.5mg-HGC-AUS": "Tacrolimus Capsules USP 0.5mg (HGC)",
    "Tacrolimus Capsules USP 0.5mg": "Tacrolimus Capsules USP 0.5mg (HGC)",
    # Different strength — kept separate.
    "Tacrolimus Cap USP 1mg-HGC-US": "Tacrolimus Capsules USP 1mg (HGC)",
    # No strength/salt form given — not assumed to match the Meglumine 20mg entry below.
    "Tafamidis (Teva)": "Tafamidis (Teva) — strength not specified",
    # Kept separate from the unspecified Teva entry above.
    "Tafamidis Meglumine 20mg Soft Capsule": "Tafamidis Meglumine 20mg Soft Capsule",
    # Combination product — kept separate from the single-ingredient Tenofovir entry below.
    "TenoDF,Lami & Dolute Tabs 300/300/50mg": "TenoDF, Lamivudine & Dolutegravir Tablets 300/300/50mg",
    # Single-ingredient — kept separate from the combination product above.
    "Tenofovir Disoproxil Fumarate [Desano]": "Tenofovir Disoproxil Fumarate (Desano)",
    "Trazodone Hydrochloride Capsules 100mg": "Trazodone Hydrochloride Capsules 100mg",
    # Ursodiol is the USAN/USP name for Ursodeoxycholic Acid — same strength/form, high confidence.
    "Ursodeoxycholic Acid 500mg Tablets": "Ursodeoxycholic Acid (Ursodiol) Tablets USP 500mg",
    "Ursodiol Tablets USP 500mg": "Ursodeoxycholic Acid (Ursodiol) Tablets USP 500mg",
    # Different strength AND form (capsule vs tablet) from the 500mg tablet group — kept separate.
    "Ursodeoxycholic Acid Capsules BP [250mg] [Hard Gelatin]": "Ursodeoxycholic Acid Capsules BP 250mg (Hard Gelatin)",
    # Different form from the oral solution below — kept separate.
    "Valganciclovir HCl USP [Aurore]": "Valganciclovir HCl USP (Aurore)",
    # Kept separate from the HCl raw-material entry above.
    "Valganciclovir for oral solution USP": "Valganciclovir for Oral Solution USP",
    # The "[125 m" entry is a truncated title (cuts off mid-word). "Vancocin" is a recognized Vancomycin brand name.
    "Vanco HCL Cap-125mg USP-HGC-2x10s- US": "Vancomycin HCl Capsules USP 125mg (HGC)",
    "Vanco Hcl Cap-125mg USP-HGC-2x10's-AVET": "Vancomycin HCl Capsules USP 125mg (HGC)",
    "Vancomycin HCl Capsules  [125mg] [HGC]": "Vancomycin HCl Capsules USP 125mg (HGC)",
    "Vancomycin Hydrochloride Capsules USP [125 m": "Vancomycin HCl Capsules USP 125mg (HGC)",
    "Vancocin125Caps-HG-3x10s-Denmark,EU": "Vancomycin HCl Capsules USP 125mg (HGC)",
    # Different strength — kept separate from the 125mg group.
    "Vanco Hcl Cap-250mg USP-HGC-2x10's-US": "Vancomycin HCl Capsules USP 250mg (HGC)",
    # No strength given in either — left unmerged with the 125mg/250mg groups rather than guessed.
    "Vancomycin HCL": "Vancomycin HCl — strength not specified",
    "Vancomycin HCl - USP-H D-ZMC": "Vancomycin HCl — strength not specified",
    # Title is truncated right after the opening bracket — no strength visible at all.
    "Vancomycin Hydrochloride Capsules [": "Vancomycin Hydrochloride Capsules — strength not specified",
    "Zinc Monomethionine IH": "Zinc Monomethionine (IH)",
    "A+C Tablets 5/12.5 mg": "A+C Tablets 5/12.5mg",
    "Acarbose tab-25mg-R2": "Acarbose Tablets 25mg",
}

