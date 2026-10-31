"""Which tasks may start together: scopes that touch, dependencies, the limit."""

from forja.orchestrator.schedule import Candidate, disjoint, startable


def task(name: str, *scope: str, after: tuple[str, ...] = ()) -> Candidate:
    return Candidate(name, scope, after)


def test_two_different_files_are_disjoint() -> None:
    assert disjoint(["a/x.py"], ["a/y.py"])


def test_the_same_file_is_not() -> None:
    assert not disjoint(["a/x.py"], ["a/x.py"])


def test_a_directory_and_a_file_in_it_touch_either_way_round() -> None:
    assert not disjoint(["a"], ["a/x.py"])
    assert not disjoint(["a/x.py"], ["a/"])


def test_a_directory_is_not_the_one_whose_name_starts_the_same() -> None:
    assert disjoint(["a"], ["ab/x.py"])


def test_the_spelling_of_case_and_separator_does_not_hide_a_touch() -> None:
    assert not disjoint(["Src\\Mod.py"], ["src/mod.py"])
    assert not disjoint(["src/mod.py."], ["src/mod.py"])


def test_with_a_limit_of_one_only_the_first_open_task_starts() -> None:
    tasks = [task("t1", "a"), task("t2", "b")]
    assert startable(tasks, [], [], [], 1) == ["t1"]
    assert startable(tasks, ["t1"], [], [], 1) == []
    assert startable(tasks, [], ["t1"], ["t1"], 1) == ["t2"]


def test_with_a_limit_of_one_a_dependency_is_not_read() -> None:
    assert startable([task("t1", "a", after=("t0",))], [], [], [], 1) == ["t1"]


def test_disjoint_tasks_start_together_up_to_the_limit() -> None:
    tasks = [task("t1", "a"), task("t2", "b"), task("t3", "c")]
    assert startable(tasks, [], [], [], 2) == ["t1", "t2"]
    assert startable(tasks, ["t1"], [], [], 2) == ["t2"]
    assert startable(tasks, ["t1", "t2"], [], [], 2) == []


def test_a_task_that_touches_a_running_one_waits() -> None:
    tasks = [task("t1", "a"), task("t2", "a/x.py"), task("t3", "c")]
    assert startable(tasks, ["t1"], [], [], 3) == ["t3"]


def test_a_task_that_touches_an_earlier_open_one_waits_even_if_that_one_waits() -> None:
    tasks = [task("t1", "a"), task("t2", "a/x.py"), task("t3", "a/x.py/deep")]
    assert startable(tasks, [], [], [], 3) == ["t1"]


def test_a_closed_task_no_longer_holds_its_scope() -> None:
    tasks = [task("t1", "a"), task("t2", "a/x.py")]
    assert startable(tasks, [], ["t1"], ["t1"], 2) == ["t2"]
    assert startable(tasks, [], [], ["t1"], 2) == ["t2"]  # blocked: closed, not integrated


def test_a_task_waits_until_its_dependencies_are_integrated() -> None:
    tasks = [task("t1", "a"), task("t2", "b", after=("t1",))]
    assert startable(tasks, ["t1"], [], [], 2) == []
    assert startable(tasks, [], ["t1"], ["t1"], 2) == ["t2"]


def test_a_task_whose_dependency_was_blocked_never_starts() -> None:
    tasks = [task("t1", "a"), task("t2", "b", after=("t1",))]
    assert startable(tasks, [], [], ["t1"], 2) == []


def test_a_running_task_is_not_chosen_again() -> None:
    assert startable([task("t1", "a")], ["t1"], [], [], 2) == []
