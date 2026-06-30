"""
Gumroad API v2 クライアント
GUMROAD_TOKEN 環境変数が必要（Gumroad Settings → Applications で取得）
"""
import os
import httpx
from pathlib import Path

GUMROAD_BASE = "https://api.gumroad.com/v2"


class GumroadClient:
    def __init__(self):
        self.token = os.environ.get("GUMROAD_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.token)

    def create_product(self, name: str, description: str, price_cents: int, published: bool = True) -> dict:
        """商品を作成してproductオブジェクトを返す"""
        resp = httpx.post(
            f"{GUMROAD_BASE}/products",
            data={
                "access_token": self.token,
                "name": name,
                "description": description,
                "price": str(price_cents),
                "published": "true" if published else "false",
            },
            timeout=30,
        )
        data = resp.json()
        if not data.get("success"):
            raise ValueError(f"Gumroad API error: {data.get('message', 'unknown')}")
        return data["product"]

    def list_products(self) -> list:
        """既存商品一覧を返す"""
        resp = httpx.get(
            f"{GUMROAD_BASE}/products",
            params={"access_token": self.token},
            timeout=30,
        )
        data = resp.json()
        if not data.get("success"):
            return []
        return data.get("products", [])

    def update_product(self, product_id: str, **kwargs) -> dict:
        """商品情報を更新する"""
        params = {"access_token": self.token, **kwargs}
        resp = httpx.put(
            f"{GUMROAD_BASE}/products/{product_id}",
            data=params,
            timeout=30,
        )
        data = resp.json()
        if not data.get("success"):
            raise ValueError(f"Update failed: {data.get('message', 'unknown')}")
        return data["product"]
