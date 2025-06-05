import os
import asyncio
import time
import threading
import uuid
import json
from typing import List, Dict, Optional
from database import Database
import requests

try:
    import pjsua2 as pj
    PJSUA_AVAILABLE = True
except ImportError:
    PJSUA_AVAILABLE = False
    print("Warning: pjsua2 not available, using mock SIP service")

class SIPCall(pj.Call if PJSUA_AVAILABLE else object):
    """SIP Call handler"""
    def __init__(self, acc, call_id=pj.PJSUA_INVALID_ID if PJSUA_AVAILABLE else -1):
        if PJSUA_AVAILABLE:
            super().__init__(acc, call_id)
        self.contact_id = None
        self.script = None
        self.webhook_url = None
        self.digit_pressed = None
        
    def onCallState(self, prm):
        """Handle call state changes"""
        if not PJSUA_AVAILABLE:
            return
            
        ci = self.getInfo()
        print(f"Call {self.contact_id}: {ci.stateText}")
        
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            # Call answered, play opening audio
            self.play_opening_audio()
        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            # Call ended
            self.handle_call_end()
    
    def onDtmfDigit(self, prm):
        """Handle DTMF digit press"""
        if not PJSUA_AVAILABLE:
            return
            
        print(f"Call {self.contact_id}: DTMF digit {prm.digit}")
        self.digit_pressed = prm.digit
        
        # Update database
        db = Database()
        db.update_contact_status(self.contact_id, 'completed', digit_pressed=prm.digit)
        
        # Play after-digit audio
        self.play_after_digit_audio()
        
        # Send webhook notification
        self.send_webhook_notification('digit_pressed', {'digit': prm.digit})
    
    def play_opening_audio(self):
        """Play opening audio file"""
        if self.script and self.script.get('opening_audio_path'):
            try:
                if PJSUA_AVAILABLE:
                    player_id = pj.Lib.instance().createPlayer(self.script['opening_audio_path'])
                    conf_port = pj.Lib.instance().getConfPortInfo(player_id).portId
                    call_conf_port = self.getConfPort()
                    pj.Lib.instance().confConnect(conf_port, call_conf_port)
                print(f"Playing opening audio: {self.script['opening_audio_path']}")
            except Exception as e:
                print(f"Error playing opening audio: {e}")
    
    def play_after_digit_audio(self):
        """Play after-digit audio file"""
        if self.script and self.script.get('after_digit_audio_path'):
            try:
                if PJSUA_AVAILABLE:
                    player_id = pj.Lib.instance().createPlayer(self.script['after_digit_audio_path'])
                    conf_port = pj.Lib.instance().getConfPortInfo(player_id).portId
                    call_conf_port = self.getConfPort()
                    pj.Lib.instance().confConnect(conf_port, call_conf_port)
                print(f"Playing after-digit audio: {self.script['after_digit_audio_path']}")
            except Exception as e:
                print(f"Error playing after-digit audio: {e}")
        
        # Hang up after playing audio
        time.sleep(2)  # Give time for audio to play
        if PJSUA_AVAILABLE:
            self.hangup(pj.CallOpParam())
    
    def handle_call_end(self):
        """Handle call termination"""
        db = Database()
        if not self.digit_pressed:
            db.update_contact_status(self.contact_id, 'no_response')
        
        self.send_webhook_notification('call_ended', {
            'digit_pressed': self.digit_pressed,
            'status': 'completed' if self.digit_pressed else 'no_response'
        })
    
    def send_webhook_notification(self, event: str, data: Dict):
        """Send webhook notification"""
        if self.webhook_url:
            try:
                payload = {
                    'event': event,
                    'contact_id': self.contact_id,
                    'call_id': str(id(self)),
                    'data': data
                }
                requests.post(f"{self.webhook_url}/sip_webhook", json=payload, timeout=5)
            except Exception as e:
                print(f"Error sending webhook: {e}")

class SIPAccount(pj.Account if PJSUA_AVAILABLE else object):
    """SIP Account handler"""
    def __init__(self):
        if PJSUA_AVAILABLE:
            super().__init__()
        self.active_calls = {}
    
    def onIncomingCall(self, prm):
        """Handle incoming calls"""
        if not PJSUA_AVAILABLE:
            return
            
        call = SIPCall(self, prm.callId)
        self.active_calls[prm.callId] = call
        
        # Auto-answer incoming calls
        call_op_param = pj.CallOpParam()
        call_op_param.statusCode = 200
        call.answer(call_op_param)

class SIPService:
    def __init__(self, sip_server: str, sip_username: str, sip_password: str, sip_port: int = 5060):
        self.sip_server = sip_server
        self.sip_username = sip_username
        self.sip_password = sip_password
        self.sip_port = sip_port
        self.db = Database()
        self.active_calls = {}
        self.lib = None
        self.account = None
        self.endpoint = None
        
        if PJSUA_AVAILABLE:
            self.init_sip()
        else:
            print("SIP service running in mock mode - no actual calls will be made")
    
    def init_sip(self):
        """Initialize SIP library and account"""
        try:
            # Create library instance
            self.lib = pj.Lib()
            
            # Initialize library
            ua_cfg = pj.UAConfig()
            ua_cfg.maxCalls = 50
            ua_cfg.threadCnt = 1
            
            media_cfg = pj.MediaConfig()
            media_cfg.clockRate = 8000
            media_cfg.sndClockRate = 8000
            
            self.lib.init(ua_cfg, media_cfg)
            
            # Start library
            self.lib.start()
            
            # Create SIP account
            self.account = SIPAccount()
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = f"sip:{self.sip_username}@{self.sip_server}"
            acc_cfg.regConfig.registrarUri = f"sip:{self.sip_server}:{self.sip_port}"
            
            # Authentication
            cred = pj.AuthCredInfo()
            cred.scheme = "digest"
            cred.realm = "*"
            cred.username = self.sip_username
            cred.data = self.sip_password
            acc_cfg.sipConfig.authCreds.append(cred)
            
            # Create account
            self.account.create(acc_cfg)
            
            print(f"SIP service initialized - connected to {self.sip_server}")
            
        except Exception as e:
            print(f"Error initializing SIP service: {e}")
            self.lib = None
    
    async def make_call(self, contact: Dict, script: Dict, webhook_url: str, caller_id: str = None) -> str:
        """Make a SIP call to a contact"""
        try:
            if not PJSUA_AVAILABLE or not self.lib:
                print(f"Mock call to {contact['phone_number']} - SIP not available")
                call_id = f"mock_{uuid.uuid4().hex[:8]}"
                self.db.update_contact_status(contact['id'], 'calling', call_id)
                return call_id
            
            # Create call
            call = SIPCall(self.account)
            call.contact_id = contact['id']
            call.script = script
            call.webhook_url = webhook_url
            
            # Make call
            dest_uri = f"sip:{contact['phone_number']}@{self.sip_server}"
            call_param = pj.CallOpParam()
            
            if caller_id:
                call_param.sipHeaders.append(pj.SipHeader("From", f"<sip:{caller_id}@{self.sip_server}>"))
            
            call.makeCall(dest_uri, call_param)
            
            call_id = str(id(call))
            self.active_calls[call_id] = call
            
            # Update contact status
            self.db.update_contact_status(contact['id'], 'calling', call_id)
            
            print(f"SIP call initiated to {contact['phone_number']}")
            return call_id
            
        except Exception as e:
            print(f"Error making SIP call to {contact['phone_number']}: {e}")
            self.db.update_contact_status(contact['id'], 'failed')
            return None
    
    async def make_campaign_calls(self, campaign_id: str, contacts: List[Dict], script: Dict, 
                                webhook_url: str, settings: Dict) -> Dict:
        """Make SIP calls to all contacts in a campaign with rate limiting"""
        results = {
            'total': len(contacts),
            'started': 0,
            'failed': 0,
            'unverified': 0,
            'invalid_numbers': 0,
            'no_funds': 0
        }
        
        concurrent_calls = settings.get('concurrent_calls', 5)
        calls_per_second = settings.get('calls_per_second', 1.0)
        caller_id = settings.get('caller_id')
        
        # Semaphore to limit concurrent calls
        semaphore = asyncio.Semaphore(concurrent_calls)
        
        async def make_single_call(contact):
            async with semaphore:
                call_id = await self.make_call(contact, script, webhook_url, caller_id)
                if call_id:
                    results['started'] += 1
                    self.db.log_call(contact['id'], campaign_id, call_id, 'started')
                else:
                    results['failed'] += 1
                
                # Rate limiting
                await asyncio.sleep(1.0 / calls_per_second)
        
        # Create tasks for all calls
        tasks = [make_single_call(contact) for contact in contacts]
        
        # Execute all calls
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
    
    def handle_call_status(self, call_id: str, call_status: str, contact_id: int = None):
        """Handle call status updates"""
        if contact_id:
            if call_status in ['completed', 'busy', 'no-answer', 'failed', 'canceled']:
                if call_status == 'completed':
                    self.db.update_contact_status(contact_id, 'no_response')
                else:
                    self.db.update_contact_status(contact_id, call_status)
                
                # Remove from active calls
                if call_id in self.active_calls:
                    del self.active_calls[call_id]
    
    def handle_digit_gather(self, contact_id: int, digit_pressed: str):
        """Handle when a digit is pressed during the call"""
        self.db.update_contact_status(contact_id, 'completed', digit_pressed=digit_pressed)
        return digit_pressed
    
    def shutdown(self):
        """Shutdown SIP service"""
        if PJSUA_AVAILABLE and self.lib:
            try:
                if self.account:
                    self.account.delete()
                self.lib.destroy()
                print("SIP service shutdown")
            except Exception as e:
                print(f"Error shutting down SIP service: {e}") 