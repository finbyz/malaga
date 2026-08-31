import frappe
import requests
# pyrefly: ignore [missing-import]
from frappe.utils import now_datetime, add_to_date


def refresh_shopify_access_token(shopify_url, client_id, client_secret):
    """
    Generate a new Shopify access token using Client Credentials Grant.
    Shopify client-credentials tokens expire after 24 hours.
    """

    url = f"https://{shopify_url.rstrip('/')}/admin/oauth/access_token"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    access_token = data.get("access_token")
    expires_in = data.get("expires_in")

    if not access_token:
        frappe.throw(
            f"Shopify did not return an access token: {data}"
        )

    setting = frappe.get_single("Shopify Setting")
    # Update ONLY the password field
    setting.set("password", access_token)
    setting.save(ignore_permissions=True)

    return {
        "access_token": access_token,
        "expires_in": expires_in,
        "expires_at": add_to_date(
            now_datetime(),
            seconds=expires_in
        ),
    }


@frappe.whitelist(allow_guest=True)
def update_shopify_token():
    shopify_url = frappe.db.get_single_value("Shopify Setting", "shopify_url")
    client_id = frappe.db.get_single_value("Shopify Setting", "custom_client_id")
    client_secret = frappe.db.get_single_value("Shopify Setting", "shared_secret")
    refresh_shopify_access_token(shopify_url, client_id, client_secret)