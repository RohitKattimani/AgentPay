"""PayPal Checkout Orders and Authorization API adapter."""

import logging
import uuid
from typing import Any, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger("agentpay.paypal")


class PayPalService:
    def __init__(self) -> None:
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.base_url = settings.PAYPAL_BASE_URL

    @property
    def mock_mode(self) -> bool:
        return not (self.client_id and self.client_secret)

    async def get_access_token(self) -> str:
        if self.mock_mode:
            return "mock_access_token"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()["access_token"]

    async def create_order(
        self,
        amount: float,
        currency: str = "USD",
        idempotency_key: Optional[str] = None,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero.")
        request_id = idempotency_key or str(uuid.uuid4())
        if self.mock_mode:
            return {
                "id": f"MOCK-ORDER-{uuid.uuid4().hex[:12].upper()}",
                "status": "CREATED",
                "mock": True,
                "approval_url": None,
            }

        token = await self.get_access_token()
        payload = {
            "intent": "AUTHORIZE",
            "purchase_units": [
                {"amount": {"currency_code": currency, "value": f"{amount:.2f}"}}
            ],
            "application_context": {
                "brand_name": "AgentPay",
                "user_action": "CONTINUE",
                "shipping_preference": "NO_SHIPPING",
                "return_url": return_url or settings.PAYPAL_RETURN_URL,
                "cancel_url": cancel_url or settings.PAYPAL_CANCEL_URL,
            },
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id,
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders", headers=headers, json=payload
            )
            response.raise_for_status()
            result = response.json()
        approval = next(
            (link.get("href") for link in result.get("links", []) if link.get("rel") == "approve"),
            None,
        )
        result["approval_url"] = approval
        result["mock"] = False
        return result

    async def authorize_order(
        self, order_id: str, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if self.mock_mode:
            return {
                "id": f"MOCK-AUTH-{uuid.uuid4().hex[:12].upper()}",
                "status": "CREATED",
                "order_id": order_id,
                "mock": True,
            }
        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders/{order_id}/authorize", headers=headers
            )
            response.raise_for_status()
            result = response.json()
        authorizations = (
            result.get("purchase_units", [{}])[0]
            .get("payments", {})
            .get("authorizations", [])
        )
        if not authorizations or not authorizations[0].get("id"):
            raise RuntimeError("PayPal did not return an authorization ID.")
        authorization = authorizations[0]
        return {
            "id": authorization["id"],
            "status": authorization.get("status", "CREATED"),
            "order_id": order_id,
            "raw": result,
            "mock": False,
        }

    async def capture_authorization(
        self, authorization_id: str, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if self.mock_mode:
            return {
                "id": f"MOCK-CAPTURE-{uuid.uuid4().hex[:12].upper()}",
                "status": "COMPLETED",
                "authorization_id": authorization_id,
                "mock": True,
            }
        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                f"{self.base_url}/v2/payments/authorizations/{authorization_id}/capture",
                headers=headers,
                json={"final_capture": True},
            )
            response.raise_for_status()
            result = response.json()
        result["mock"] = False
        return result


paypal_service = PayPalService()
