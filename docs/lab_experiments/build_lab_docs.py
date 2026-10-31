"""
Builds the ten Research Methodology & IPR Lab experiment documents from the department templates
and the frozen research outputs (tag paper-audit-v1).

    python docs/lab_experiments/build_lab_docs.py

Templates: docs/lab_experiments/templates/ (copies of the department's Experiment 1-5 templates).
Outputs:   docs/lab_experiments/Experiment_NN_*.docx and docs/lab_experiments/figures/.
"""

import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
logging.disable(logging.INFO)

import docx  # noqa: E402

import exp_1_5  # noqa: E402
import exp_6_10  # noqa: E402
import lab_data  # noqa: E402
import lab_figures  # noqa: E402

TPL = os.path.join(HERE, "templates")
FIG = os.path.join(HERE, "figures")
TEMPLATES = {
    1: "Experiment 1_Template_Research_Problem_and_Gap_Analysis.docx",
    2: "Experiment 2_Template_Research_Planning_and_Methodology_Design.docx",
    3: "Experiment_3_Template_Dataset_Experimental_Setup_Preparation.docx",
    4: "Experiment_4_Implementation and Experimental Validation.docx",
    5: "Experiment_5_Data Analysis and Visualization.docx",
}
OUTPUTS = {
    1: "Experiment_01_Research_Problem_and_Gap_Analysis.docx",
    2: "Experiment_02_Research_Planning_and_Methodology_Design.docx",
    3: "Experiment_03_Dataset_and_Experimental_Setup.docx",
    4: "Experiment_04_Implementation_and_Experimental_Validation.docx",
    5: "Experiment_05_Data_Analysis_and_Visualization.docx",
    6: "Experiment_06_Technical_Paper_Preparation.docx",
    7: "Experiment_07_Plagiarism_Peer_Review_and_Revision.docx",
    8: "Experiment_08_Prior_Art_Search.docx",
    9: "Experiment_09_IPR_Document_Copyright_Registration.docx",
    10: "Experiment_10_Research_Dissemination_and_Showcase.docx",
}


def check(path: str) -> list:
    """Return problems: leftover template blanks (____) or empty template placeholders."""
    d = docx.Document(path)
    texts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            texts.extend(c.text for c in row.cells)
    problems = [t for t in texts if "____" in t]
    problems += [t for t in texts if "[Insert" in t]
    return problems


def main() -> None:
    os.makedirs(FIG, exist_ok=True)
    print("Loading research outputs and timing backtests...")
    d = lab_data.load()
    figs = lab_figures.copy_paper_figures(FIG)
    figs.update({
        "workflow": lab_figures.workflow(FIG),
        "rop_ci": lab_figures.rop_ci_by_method(d, FIG),
        "return_vs_method": lab_figures.returns_vs_method(d, FIG),
        "boxplot": lab_figures.rop_boxplot(d, FIG),
        "confusion": lab_figures.confusion_matrix(d, FIG),
    })
    figs["poster"] = lab_figures.poster(d, figs, FIG)

    out = {k: os.path.join(HERE, v) for k, v in OUTPUTS.items()}
    tpl = {k: os.path.join(TPL, v) for k, v in TEMPLATES.items()}
    exp_1_5.build_exp1(d, tpl[1], out[1])
    exp_1_5.build_exp2(d, tpl[2], out[2], figs["workflow"])
    exp_1_5.build_exp3(d, tpl[3], out[3])
    exp_1_5.build_exp4(d, tpl[4], out[4], figs)
    exp_1_5.build_exp5(d, tpl[5], out[5], figs)
    exp_6_10.build_exp6(d, tpl[1], out[6], figs)
    exp_6_10.build_exp7(d, tpl[1], out[7])
    exp_6_10.build_exp8(d, tpl[1], out[8])
    exp_6_10.build_exp9(d, tpl[1], out[9])
    exp_6_10.build_exp10(d, tpl[1], out[10], figs)

    failed = False
    for k, path in out.items():
        problems = check(path)
        status = "OK" if not problems else f"{len(problems)} unfilled blanks"
        failed |= bool(problems)
        print(f"Experiment {k:2d}: {os.path.basename(path)} — {status}")
        for p in problems[:5]:
            print("     ", p[:120])
    if failed:
        raise SystemExit("Some template blanks were not filled.")


if __name__ == "__main__":
    main()
