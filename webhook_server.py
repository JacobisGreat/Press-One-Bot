from flask import Flask, request, Response, jsonify
import os
from database import Database
from sip_service import SIPService
import json

app = Flask(__name__)
db = Database()

# Initialize SIP service
sip_service = SIPService(
    sip_server=os.getenv('SIP_SERVER'),
    sip_username=os.getenv('SIP_USERNAME'),
    sip_password=os.getenv('SIP_PASSWORD'),
    sip_port=int(os.getenv('SIP_PORT', 5060))
)

@app.route('/sip_webhook', methods=['POST'])
def sip_webhook_handler():
    """Handle SIP webhook events"""
    try:
        data = request.get_json()
        event = data.get('event')
        contact_id = data.get('contact_id')
        call_id = data.get('call_id')
        event_data = data.get('data', {})
        
        print(f"SIP Webhook: {event} for contact {contact_id}")
        
        if event == 'digit_pressed':
            digit = event_data.get('digit')
            print(f"Contact {contact_id} pressed digit: {digit}")
            
        elif event == 'call_ended':
            status = event_data.get('status')
            digit_pressed = event_data.get('digit_pressed')
            print(f"Call ended for contact {contact_id}: {status}")
            
            # Update call log
            if contact_id:
                db.update_contact_status(contact_id, status, digit_pressed=digit_pressed)
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        print(f"Error handling SIP webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return {'status': 'healthy', 'service': 'sip-call-bot-webhook'}

@app.route('/sip_status', methods=['GET'])
def sip_status():
    """SIP service status"""
    return {
        'sip_server': os.getenv('SIP_SERVER'),
        'sip_username': os.getenv('SIP_USERNAME'),
        'sip_port': os.getenv('SIP_PORT', 5060),
        'status': 'connected' if sip_service.lib else 'disconnected'
    }

if __name__ == '__main__':
    # This is for development only
    # In production, use a proper WSGI server like gunicorn
    app.run(host='0.0.0.0', port=5000, debug=True) 