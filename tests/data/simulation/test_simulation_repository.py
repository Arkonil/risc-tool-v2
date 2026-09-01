from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import DataSourceID
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import ScalarConfig
from risc_tool_v2.data.simulation.models.simulation import SimulationStatus
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfig,
    SimulationConfigGenerator,
)
from risc_tool_v2.data.simulation.repositories.simulation_repository import (
    SimulationRepository,
)


def _make_sc() -> SimulationConfig:
    return SimulationConfig(
        risk_segment_config=RiskSegmentConfig(),
        dev_unit_bad_rate=BadRateConfig(
            loss_rate_type=LossRateTypes.ULR,
            numerator_col="unt_bad",
            data_source_ids=(DataSourceID(int=1),),
            is_annualized=True,
        ),
        dev_dollar_bad_rate=None,
        test_unit_bad_rate=None,
        test_dollar_bad_rate=None,
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=ScalarConfig(),
        variable_name="credit_score",
        variable_type=VariableType.NUMERICAL,
    )


def _make_scg() -> SimulationConfigGenerator:
    return SimulationConfigGenerator(name="base", **_sc_fields())


def _sc_fields() -> dict:
    sc = _make_sc()
    return {
        "risk_segment_config": sc.risk_segment_config,
        "dev_unit_bad_rate": sc.dev_unit_bad_rate,
        "dev_dollar_bad_rate": sc.dev_dollar_bad_rate,
        "test_unit_bad_rate": sc.test_unit_bad_rate,
        "test_dollar_bad_rate": sc.test_dollar_bad_rate,
        "bad_rate_type": sc.bad_rate_type,
        "scalar_config": sc.scalar_config,
        "filter_ids": sc.filter_ids,
        "remove_outliers": sc.remove_outliers,
        "variable_name": sc.variable_name,
        "variable_type": sc.variable_type,
        "auto_band": sc.auto_band,
        "use_scalars": sc.use_scalars,
    }


def test_create_and_get_simulation(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scg = _make_scg()

    sim = repo.create_simulation(scg)

    assert sim.simulation_config_generator.uid == scg.uid
    assert sim.status == SimulationStatus.PENDING
    assert sim.uid in repo.simulations
    assert repo.get_simulation(sim.uid).uid == sim.uid


def test_created_simulations_get_unique_ids(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scg = _make_scg()

    sim1 = repo.create_simulation(scg)
    sim2 = repo.create_simulation(scg)

    assert sim1.uid != sim2.uid


def test_run_simulation_produces_output_and_caches(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg())
    generated_sc = sim.simulation_config_generator.get_configs()[0]

    first = repo.run_simulation(sim.uid)
    second = repo.run_simulation(sim.uid)

    assert first.status == SimulationStatus.COMPLETED
    assert first.output is not None
    assert second.output is not None
    assert first.output.uid == second.output.uid
    assert generated_sc.uid in repo.scs


def test_remove_simulation_cleans_up(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg())
    scg_uid = sim.simulation_config_generator.uid

    repo.remove_simulation(sim.uid)

    assert sim.uid not in repo.simulations
    assert scg_uid not in repo.scgs
