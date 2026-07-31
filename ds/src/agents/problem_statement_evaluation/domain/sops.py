# agents/problem_statement_evaluation/domain/sops.py

# 13 SOPs each for Deviation, OOS, OOT
DEVIATION_SOPS = [
    "All immediate on-the-spot actions (including quarantine of material if applicable) taken have been listed",
    "Appropriate actions taken on affected areas as identified in Initial impact assessment.",
    "Evidence has been cited on sufficiency of the immediate steps to contain the non-conformance.",
    "Immediately quarantine the equipment used in analysis, suspect sample and retain all related reference standards, control samples, and reagent batches used in testing",
    "Secure all original raw data, worksheets, chromatograms, intrument printouts and caliberation records associated with failed test",
    "Review of related records, procedures etc. as per preliminary investigation checklist.",
    "Perform the Gemba/ talk to people involved in the activity.",
    "Document preliminary observations.",
    "Ensure all findings, actions and decisions are documented with timestamps and signatures.",
    "Cite specific evidence demonstrating that immediate actions were adequate to prevent "
    "further non-conformance and distribute of non-conforming product.",
    "Clearly identify all affected batches, lot numbers and distributed quantities.",
    "Immediately quaratine all affected batch/lot material and place on 'Do Not Use' status pending "
    "investigation completion.",
    "Document all immediate on-the-spot actions taken halt production if applicable, segregate affected material, implement temporary controls, prevent further non-conforming product distribution"
]

OOS_SOPS = [
    "All immediate on-the-spot actions (including quarantine of material if applicable) taken have been listed",
    "Appropriate actions taken on affected areas as identified in Initial impact assessment.",
    "Evidence has been cited on sufficiency of the immediate steps to contain the non-conformance.",
    "Immediately quarantine the equipment used in analysis, suspect sample and retain all related reference standards, control samples, and reagent batches used in testing",
    "Secure all original raw data, worksheets, chromatograms, intrument printouts and caliberation records associated with failed test",
    "Review of related records, procedures etc. as per preliminary investigation checklist.",
    "Perform the Gemba/ talk to people involved in the activity.",
    "Document preliminary observations.",
    "Ensure all findings, actions and decisions are documented with timestamps and signatures.",
    "Cite specific evidence demonstrating that immediate actions were adequate to prevent "
    "further non-conformance and distribute of non-conforming product.",
    "Clearly identify all affected batches, lot numbers and distributed quantities.",
    "Immediately quaratine all affected batch/lot material and place on 'Do Not Use' status pending "
    "investigation completion.",
    "Document all immediate on-the-spot actions taken halt production if applicable, segregate affected material, implement temporary controls, prevent further non-conforming product distribution"
]

OOT_SOPS = [
    "All immediate on-the-spot actions (including quarantine of material if applicable) taken have been listed",
    "Appropriate actions taken on affected areas as identified in Initial impact assessment.",
    "Evidence has been cited on sufficiency of the immediate steps to contain the non-conformance.",
    "Immediately quarantine the equipment used in analysis, suspect sample and retain all related reference standards, control samples, and reagent batches used in testing",
    "Secure all original raw data, worksheets, chromatograms, intrument printouts and caliberation records associated with failed test",
    "Review of related records, procedures etc. as per preliminary investigation checklist.",
    "Perform the Gemba/ talk to people involved in the activity.",
    "Document preliminary observations.",
    "Ensure all findings, actions and decisions are documented with timestamps and signatures.",
    "Cite specific evidence demonstrating that immediate actions were adequate to prevent "
    "further non-conformance and distribute of non-conforming product.",
    "Clearly identify all affected batches, lot numbers and distributed quantities.",
    "Immediately quaratine all affected batch/lot material and place on 'Do Not Use' status pending "
    "investigation completion.",
    "Document all immediate on-the-spot actions taken halt production if applicable, segregate affected material, implement temporary controls, prevent further non-conforming product distribution"
]

MARKET_COMPLIANT_SOPS = [
    "Immediately evaluate the complaint for potential safety risk (serious adverse event, injury, poisoning, allergic reaction);",
    "if safety-critical, escalate to Medical/Regulatory immediately.",
    "Review of reserve samples for complaint batch, a minimum of two preceding & succeeding",
    "Review of raw data associated with affected batch",
    "Review of batch distribution",
    "Notification to other sites",
    "Categorize complaint type (manufacturing defect, stability issue, contamination, labeling error, packaging defect, suspected adverse event, etc.) to guide investigation approach.",
    "Request the original product/complaint sample from the complainant with proper chain of custody procedures; provide prepaid shipping materials if necessary.",
    "Provide acknowledgement to complainant; document all communications, obtain additional information if needed, and assure confidentiality/follow-up.",
    "Notify QA, Manufacturing, Ragulatory Affairs, Medical Affairs, and relevant departments; schedule initial complaint review meeting to plan investigation strategy."
]

SOP_BY_EVENT_TYPE = {
    "Deviation": DEVIATION_SOPS,
    "OOS": OOS_SOPS,
    "OOT": OOT_SOPS,
    "Market Complaint": MARKET_COMPLIANT_SOPS
}