from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.skip_decorator import skip

@skip(reason="Skipping this test for testing purposes")
@jpipe(consume=["enable_feature"], produce=["feature_result"])
def optional_feature(enable_feature: bool, produce) -> bool:
    """Optional feature that can be skipped"""
    if enable_feature:
        produce("feature_result", "enabled")
        return True
    return False

@jpipe(consume=["feature_result"])
def use_feature_result(feature_result: str) -> bool:
    """Use the feature result"""
    return feature_result == "enabled"
