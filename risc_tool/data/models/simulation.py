# import typing as t

# from pydantic import BaseModel, Field, model_validator

# from risc_tool.data.models.enums import LossRateTypes, VariableType
# from risc_tool.data.models.uid import DataSourceID, FilterID


# class RiskSegment(BaseModel):
#     name: str = Field(min_length=1)
#     upper_rate: float = Field(gt=0)
#     bg_color: str = "#3D8F3D"
#     font_color: str = "#FFFFFF"
#     maf_dlr: float = 1.0
#     maf_ulr: float = 1.0
#     selected: bool = True


# class RiskSegmentConfig(BaseModel):
#     segments: list[RiskSegment]

#     @classmethod
#     def default(cls) -> t.Self:
#         return cls(
#             segments=[
#                 RiskSegment(name="Low", upper_rate=0.02, bg_color="#3D8F3D"),
#                 RiskSegment(name="Medium", upper_rate=0.05, bg_color="#F2C94C"),
#                 RiskSegment(name="High", upper_rate=1.0, bg_color="#EB5757"),
#             ]
#         )


# class BadRateScalar(BaseModel):
#     """Scalar rates for annualization and risk scalar factor computation.

#     Attributes:
#         loss_rate_type: Type of loss rate ($ Bad Rate or # Bad Rate).
#         current_rate: Current MOB loss rate as a decimal (or None if unconfigured).
#         lifetime_rate: Lifetime MOB loss rate as a decimal (or None if unconfigured).
#     """

#     bad_rate_type: LossRateTypes
#     current_rate: float | None = None
#     lifetime_rate: float | None = None


# class ScalarConfig(BaseModel):
#     unt_scalar: BadRateScalar = BadRateScalar(bad_rate_type=LossRateTypes.ULR)
#     dlr_scalar: BadRateScalar = BadRateScalar(bad_rate_type=LossRateTypes.DLR)


# class BadRateConfig(BaseModel):
#     dev_datasource_ids: list[DataSourceID] = Field(default_factory=list[DataSourceID])
#     dev_unt_num_col: str | None = None
#     dev_dlr_num_col: str | None = None
#     dev_dlr_den_col: str | None = None
#     dev_mob: int = Field(ge=1, default=12)
#     tst_datasource_ids: list[DataSourceID] = Field(default_factory=list[DataSourceID])
#     tst_unt_num_col: str | None = None
#     tst_dlr_num_col: str | None = None
#     tst_dlr_den_col: str | None = None
#     lifetime_mob: int = Field(ge=1, default=36)

#     @model_validator(mode="after")
#     def validate_lifetime_mob(self) -> t.Self:
#         if self.lifetime_mob < self.dev_mob:
#             raise ValueError("lifetime_mob must be greater than or equal to dev_mob")
#         return self


# class SimulationConfig(BaseModel):
#     risk_segment_config: RiskSegmentConfig = Field(
#         default_factory=RiskSegmentConfig.default
#     )
#     scalar_config: ScalarConfig = ScalarConfig()
#     bad_rate_type: LossRateTypes = LossRateTypes.DLR
#     bad_rate_config: BadRateConfig = BadRateConfig()
#     auto_band: bool = True
#     use_scalars: bool = True
#     filter_ids: set[FilterID] = Field(default_factory=set[FilterID])
#     remove_outliers: bool = True
#     input_variable_name: str | None = None
#     input_variable_type: VariableType = VariableType.NUMERICAL


# config = SimulationConfig()
