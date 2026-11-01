from typing import Optional, Dict, Any, Tuple
from domains.notifications.domain.entities import AlertRule
from domains.notifications.domain.value_objects import ConditionType


class RuleMatcherDomainService:
    """Pure domain service for evaluating symbol-level market data against alert rule conditions.

    Rules are symbol-level: price rules compare against the underlying's spot price and
    IV rules against the at-the-money implied volatility in percent.
    """

    @staticmethod
    def match(rule: AlertRule, payload: Dict[str, Any]) -> Tuple[Optional[bool], Optional[float], Optional[str]]:
        """Evaluate whether the rule's condition currently holds.

        Returns (condition_met, actual_value, message). condition_met is None when the payload
        lacks the value the rule needs, so the rule's crossing state must not change.
        """
        if not rule.is_active:
            return None, None, None

        cond = rule.condition_type

        if cond in (ConditionType.ABOVE_PRICE, ConditionType.BELOW_PRICE):
            spot = payload.get("spot_price")
            if spot is None:
                spot = payload.get("last_price")
            if spot is None:
                return None, None, None
            spot = float(spot)
            if cond == ConditionType.ABOVE_PRICE:
                met = spot > rule.threshold
                msg = f"{rule.symbol} price {spot:.2f} crossed above {rule.threshold}"
            else:
                met = spot < rule.threshold
                msg = f"{rule.symbol} price {spot:.2f} dropped below {rule.threshold}"
            return met, spot, msg

        if cond == ConditionType.IV_SPIKE:
            iv = payload.get("atm_iv_pct")
            if iv is None:
                iv = payload.get("implied_volatility")
            if iv is None:
                return None, None, None
            iv = float(iv)
            msg = f"{rule.symbol} ATM implied volatility {iv:.2f}% rose to or above {rule.threshold}%"
            return iv >= rule.threshold, iv, msg

        return None, None, None
