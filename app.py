import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from dotenv import load_dotenv

load_dotenv()

ERPNEXT_URL = os.getenv("ERPNEXT_URL")
ERPNEXT_API_KEY = os.getenv("ERPNEXT_API_KEY")
ERPNEXT_API_SECRET = os.getenv("ERPNEXT_API_SECRET")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
PORT = int(os.getenv("PORT", 5001))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lead-api")

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGIN}})


@app.route("/api/lead", methods=["POST"])
def create_lead():
    try:
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        phone = (body.get("phone") or "").strip()
        email = (body.get("email") or "").strip()
        message = (body.get("message") or "").strip()

        if not name or not phone:
            return jsonify({"error": "Missing required fields"}), 400

        if not ERPNEXT_URL or not ERPNEXT_API_KEY or not ERPNEXT_API_SECRET:
            logger.error("ERPNext credentials not configured")
            return jsonify({"error": "Server configuration error"}), 500

        name_parts = name.split(" ")
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) or first_name

        auth_header = f"token {ERPNEXT_API_KEY}:{ERPNEXT_API_SECRET}"

        lead_payload = {
            "first_name": first_name,
            "last_name": last_name,
            "mobile_no": phone,
            "source": "Website",
            "request_type": "Other",
        }

        if email:
            lead_payload["email"] = email

        resp = requests.post(
            f"{ERPNEXT_URL}/api/resource/CRM Lead",
            headers={
                "Content-Type": "application/json",
                "Authorization": auth_header,
            },
            json=lead_payload,
            timeout=15,
        )

        result = {}
        try:
            result = resp.json()
        except ValueError:
            pass

        if not resp.ok:
            logger.error("ERPNext error: %s", result)
            return jsonify({"error": "Failed to create lead"}), 502

        lead_id = (result.get("data") or {}).get("name")

        # Attach the visitor's message as a linked Note on the lead.
        if lead_id and message:
            try:
                timestamp_label = datetime.now().strftime("%b %d, %Y %I:%M %p")
                note_payload = {
                    "doctype": "FCRM Note",
                    "reference_doctype": "CRM Lead",
                    "reference_docname": lead_id,
                    "title": f"Website Enquiry - {timestamp_label}",
                    "content": f"<p>{message}</p>",
                }
                note_resp = requests.post(
                    f"{ERPNEXT_URL}/api/resource/FCRM Note",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": auth_header,
                    },
                    json=note_payload,
                    timeout=15,
                )
                if not note_resp.ok:
                    logger.error("Note creation failed: %s", note_resp.text)
            except requests.RequestException:
                logger.exception("Note creation request failed")

        return jsonify({"success": True, "leadId": lead_id})

    except requests.RequestException as e:
        logger.exception("ERPNext request failed")
        return jsonify({"error": "Something went wrong"}), 500
    except Exception as e:
        logger.exception("Contact API error")
        return jsonify({"error": "Something went wrong"}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT)