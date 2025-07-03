"""Notebook"""

from jpipe_runner import Consume, Produce

fake_fs = {
    "notebook.ipynb": {
        "pep8_standard": True,
        "linear_exec_order": True,
    },
    "README.md": {},
}


@Consume("notebook")
@Produce("pep8_standart_result")
def check_pep8_coding_standard(notebook: str, produce):
    res = fake_fs[notebook]["pep8_standard"]
    produce("pep8_standart_result", res)
    return res


@Consume("notebook")
@Produce("linear_exec_order")
def verify_notebook_has_linear_execution_order(notebook: str, produce):
    res = fake_fs[notebook]["linear_exec_order"]
    produce("linear_exec_order", res)
    return res


@Consume("pep8_standart_result", "linear_exec_order")
def assess_quality_gates_are_met(pep8_standart_result, linear_exec_order):
    print("Assessing all quality gates!")
    return all([
        pep8_standart_result,
        linear_exec_order,
    ])


@Consume("notebook")
def notebook_file_exists(notebook: str):
    if notebook not in fake_fs:
        raise FileNotFoundError(f"notebook '{notebook}' not found")
    return True
