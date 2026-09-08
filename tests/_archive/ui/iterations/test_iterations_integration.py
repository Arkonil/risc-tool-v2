"""Integration tests for iterations workflows and data pipeline evaluation."""

from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.ui.iterations.iterations_vm import IterationsViewModel


def test_full_single_var_flow_integration():
    d = DataRepository()
    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)
    vm = IterationsViewModel(d, i, o, f, m, s)

    assert vm.iterations == {}
