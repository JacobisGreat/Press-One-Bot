import os
import logging
import pandas as pd
import io
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from database import Database
from sip_service import SIPService

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database and services
db = Database()
sip_service = SIPService(
    sip_server=os.getenv('SIP_SERVER'),
    sip_username=os.getenv('SIP_USERNAME'),
    sip_password=os.getenv('SIP_PASSWORD'),
    sip_port=int(os.getenv('SIP_PORT', 5060))
)

# Webhook URL for Twilio callbacks (you'll need to update this with your actual URL)
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-domain.com')

# User session data
user_sessions = {}

class CallBot:
    def __init__(self):
        self.application = None
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user_id = update.effective_user.id
        await update.message.reply_text(
            "P1 bot\n\n"
            "Your personal call campaign commands:\n"
            "/call - Start your call campaign with CSV file\n"
            "/recall - Recall your contacts who didn't press a digit\n"
            "/script - Manage your call scripts\n"
            "/settings - Configure your call parameters\n"
            "/help - Show this help message\n\n"
            "🔒 All your data is private and isolated from other users."
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command handler"""
        help_text = """
🤖 *Call Campaign Bot Help*

*Commands:*

📞 */call* - Upload a CSV file with format: name|email|phonenumber
   The bot will start calling all contacts in the file.

🔄 */recall* - Recall all contacts from the last campaign who didn't press any digit during the IVR.

📝 */script* - Manage your call scripts:
   • View existing scripts
   • Create new scripts
   • Upload opening and after-digit audio files (MP3)

⚙️ */settings* - Configure call parameters:
   • Concurrent calls (max simultaneous calls)
   • Calls per second (rate limiting)
   • Caller ID (phone number to display)
   • Active script selection

*CSV Format:*
```
name,email,phonenumber
John Doe,john@example.com,+1234567890
Jane Smith,jane@example.com,+9876543210
```

*Note:* Make sure your Twilio account is properly configured and you have a valid webhook URL set up.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def call_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /call command"""
        user_id = update.effective_user.id
        
        await update.message.reply_text(
            "📞 *Call Campaign*\n\n"
            "Please upload a CSV file with the following format:\n"
            "`name,email,phonenumber`\n\n"
            "Example:\n"
            "```\n"
            "John Doe,john@example.com,+1234567890\n"
            "Jane Smith,jane@example.com,+9876543210\n"
            "```",
            parse_mode='Markdown'
        )
        
        # Set user state to waiting for CSV
        user_sessions[user_id] = {'state': 'waiting_for_csv', 'command': 'call'}
    
    async def recall_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /recall command"""
        user_id = update.effective_user.id
        
        # Get the last campaign for this user (simplified - using a default campaign ID)
        campaign_id = f"user_{user_id}_campaign"
        
        # Get contacts who didn't press any digit
        contacts_to_recall = db.get_contacts_without_digit_press(campaign_id)
        
        if not contacts_to_recall:
            await update.message.reply_text(
                "📞 No contacts found to recall.\n"
                "Either all contacts pressed a digit or no previous campaign exists."
            )
            return
        
        # Reset their status to pending
        contact_ids = [contact['id'] for contact in contacts_to_recall]
        db.reset_contacts_for_recall(contact_ids)
        
        await update.message.reply_text(
            f"🔄 Found {len(contacts_to_recall)} contacts to recall.\n"
            f"Starting recall campaign..."
        )
        
        # Start the recall campaign
        await self.start_campaign(update, user_id, campaign_id, contacts_to_recall)
    
    async def script_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /script command"""
        user_id = update.effective_user.id
        
        # Get existing scripts for this user
        scripts = db.get_scripts(user_id)
        
        keyboard = []
        
        # Add existing scripts
        for script in scripts:
            keyboard.append([InlineKeyboardButton(
                f"📝 {script['name']}", 
                callback_data=f"script_view_{script['id']}"
            )])
        
        # Add option to create new script
        keyboard.append([InlineKeyboardButton("➕ Create New Script", callback_data="script_new")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        script_count = len(scripts)
        await update.message.reply_text(
            f"📝 *Your Script Management* ({script_count} scripts)\n\n"
            "Select a script to view/edit or create a new one:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user_id = update.effective_user.id
        
        # Get current settings
        settings = db.get_user_settings(user_id)
        
        settings_text = f"""
⚙️ *Current Settings*

📞 Concurrent Calls: {settings['concurrent_calls']}
⏱️ Calls per Second: {settings['calls_per_second']}
📱 Caller ID: {settings['caller_id'] or 'Default'}
📝 Active Script: {settings['active_script_id'] or 'None'}
        """
        
        keyboard = [
            [InlineKeyboardButton("📞 Set Concurrent Calls", callback_data="settings_concurrent")],
            [InlineKeyboardButton("⏱️ Set Calls per Second", callback_data="settings_rate")],
            [InlineKeyboardButton("📱 Set Caller ID", callback_data="settings_caller_id")],
            [InlineKeyboardButton("📝 Select Active Script", callback_data="settings_script")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            settings_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file uploads"""
        user_id = update.effective_user.id
        
        logger.info(f"File uploaded by user {user_id}")
        logger.info(f"Current user sessions: {user_sessions}")
        
        if user_id not in user_sessions:
            logger.warning(f"No session found for user {user_id}")
            await update.message.reply_text("Please use a command first.")
            return
        
        session = user_sessions[user_id]
        logger.info(f"User {user_id} session state: {session.get('state')}")
        
        if session.get('state') == 'waiting_for_csv':
            logger.info("Processing CSV upload")
            await self.handle_csv_upload(update, context)
        elif session.get('state') == 'waiting_for_opening_audio':
            logger.info("Processing opening audio upload")
            await self.handle_audio_upload(update, context, 'opening')
        elif session.get('state') == 'waiting_for_after_digit_audio':
            logger.info("Processing after digit audio upload")
            await self.handle_audio_upload(update, context, 'after_digit')
        else:
            logger.warning(f"Unknown state: {session.get('state')}")
            await update.message.reply_text(f"Unknown state: {session.get('state')}. Please start over.")
    
    async def handle_csv_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle CSV file upload for call campaign"""
        user_id = update.effective_user.id
        
        try:
            # Get the file
            file = await update.message.document.get_file()
            file_content = await file.download_as_bytearray()
            
            # Parse CSV
            csv_content = file_content.decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_content))
            
            # Validate CSV format
            required_columns = ['name', 'phonenumber']
            if not all(col in df.columns for col in required_columns):
                await update.message.reply_text(
                    "❌ Invalid CSV format. Required columns: name, phonenumber\n"
                    "Optional column: email"
                )
                return
            
            # Convert to list of dictionaries
            contacts = df.to_dict('records')
            
            # Create campaign ID
            campaign_id = f"user_{user_id}_campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Save contacts to database
            inserted = db.add_contacts_from_csv(campaign_id, contacts)
            
            await update.message.reply_text(
                f"✅ Successfully imported {inserted} contacts.\n"
                f"Starting call campaign..."
            )
            
            # Get pending contacts and start campaign
            pending_contacts = db.get_pending_contacts(campaign_id)
            await self.start_campaign(update, user_id, campaign_id, pending_contacts)
            
        except Exception as e:
            logger.error(f"Error processing CSV: {e}")
            await update.message.reply_text(
                f"❌ Error processing CSV file: {str(e)}\n"
                "Please check the file format and try again."
            )
        finally:
            # Clear session
            if user_id in user_sessions:
                del user_sessions[user_id]
    
    async def handle_audio_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE, audio_type: str):
        """Handle audio file upload for scripts"""
        user_id = update.effective_user.id
        
        try:
            # Send processing message first
            processing_msg = await update.message.reply_text("🔄 Processing audio file...")
            
            # Create audio directory if it doesn't exist
            os.makedirs('audio', exist_ok=True)
            
            # Get the file - handle both document and audio types
            if update.message.document:
                file = await update.message.document.get_file()
                original_filename = update.message.document.file_name or "audio.mp3"
            elif update.message.audio:
                file = await update.message.audio.get_file()
                original_filename = update.message.audio.file_name or "audio.mp3"
            else:
                await processing_msg.delete()
                await update.message.reply_text("❌ Could not process the audio file. Please try again.")
                return
            
            # Generate filename
            session = user_sessions[user_id]
            script_name = session.get('script_name', 'default')
            filename = f"audio/{script_name}_{audio_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
            
            # Download file
            await file.download_to_drive(filename)
            
            # Delete processing message
            await processing_msg.delete()
            
            # Update session with file path
            session[f'{audio_type}_audio_path'] = filename
            
            if audio_type == 'opening':
                await update.message.reply_text(
                    "✅ Opening audio saved successfully!\n"
                    f"📁 File: {filename}\n\n"
                    "Now please upload the 'after digit press' audio file (MP3):"
                )
                session['state'] = 'waiting_for_after_digit_audio'
            else:  # after_digit
                # Check if this is an update or new script
                if session.get('updating') and session.get('script_id'):
                    # Update existing script
                    script_id = session['script_id']
                    script = db.get_script(user_id, script_id)
                    
                    if script:
                        if audio_type == 'opening':
                            db.save_script(user_id, script['name'], filename, script.get('after_digit_audio_path'))
                        else:
                            db.save_script(user_id, script['name'], script.get('opening_audio_path'), filename)
                        
                        await update.message.reply_text(
                            f"✅ Script '{script['name']}' updated successfully!\n"
                            f"📁 {audio_type.replace('_', ' ').title()} audio: {filename}"
                        )
                    else:
                        await update.message.reply_text("❌ Script not found or you don't have permission to edit it.")
                else:
                    # Save the complete new script
                    script_id = db.save_script(
                        user_id=user_id,
                        name=session['script_name'],
                        opening_audio_path=session.get('opening_audio_path'),
                        after_digit_audio_path=session.get('after_digit_audio_path')
                    )
                    
                    await update.message.reply_text(
                        f"🎉 Your script '{session['script_name']}' created successfully!\n"
                        f"📁 Opening audio: {session.get('opening_audio_path', 'Not set')}\n"
                        f"📁 After digit audio: {session.get('after_digit_audio_path', 'Not set')}\n"
                        f"🆔 Script ID: {script_id}\n\n"
                        "You can now use this script for call campaigns!"
                    )
                
                # Clear session
                if user_id in user_sessions:
                    del user_sessions[user_id]
        
        except Exception as e:
            logger.error(f"Error processing audio file: {e}")
            await update.message.reply_text(
                f"❌ Error processing audio file: {str(e)}\n"
                "Please make sure you're uploading a valid MP3 file and try again."
            )
    
    async def start_campaign(self, update: Update, user_id: int, campaign_id: str, contacts: list):
        """Start a call campaign"""
        try:
            # Get user settings and active script
            settings = db.get_user_settings(user_id)
            
            script = None
            if settings['active_script_id']:
                script = db.get_script(user_id, settings['active_script_id'])
            
            if not script:
                # Use first available script if no active script set
                scripts = db.get_scripts(user_id)
                script = scripts[0] if scripts else None
            
            if not script:
                await update.message.reply_text(
                    "❌ No script available. Please create a script first using /script"
                )
                return
            
            # Start the campaign
            await update.message.reply_text(
                f"📞 Starting your campaign with {len(contacts)} contacts...\n"
                f"Script: {script['name']}\n"
                f"Concurrent calls: {settings['concurrent_calls']}\n"
                f"Calls per second: {settings['calls_per_second']}"
            )
            
            # Make the calls
            results = await sip_service.make_campaign_calls(
                campaign_id, contacts, script, WEBHOOK_URL, settings
            )
            
            # Build detailed results message
            result_msg = f"✅ Your campaign completed!\n"
            result_msg += f"📊 **Results Summary:**\n"
            result_msg += f"└ Total contacts: {results['total']}\n"
            result_msg += f"└ Calls started: {results['started']}\n"
            
            if results['unverified'] > 0:
                result_msg += f"⚠️ Unverified numbers: {results['unverified']}\n"
                result_msg += f"   (Trial account limitation)\n"
            
            if results['invalid_numbers'] > 0:
                result_msg += f"❌ Invalid numbers: {results['invalid_numbers']}\n"
            
            if results['no_funds'] > 0:
                result_msg += f"💰 Insufficient funds: {results['no_funds']}\n"
            
            if results['failed'] > 0:
                result_msg += f"🔴 Other failures: {results['failed']}\n"
            
            # Add help message for trial accounts
            if results['unverified'] > 0:
                result_msg += f"\n💡 **Trial Account Help:**\n"
                result_msg += f"• Verify numbers in Twilio Console\n"
                result_msg += f"• Or upgrade to paid account\n"
                result_msg += f"• Visit: https://console.twilio.com"
            
            await update.message.reply_text(result_msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error starting campaign: {e}")
            await update.message.reply_text(
                f"❌ Error starting campaign: {str(e)}"
            )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data.startswith('script_'):
            await self.handle_script_callback(query, user_id, data)
        elif data.startswith('settings_'):
            await self.handle_settings_callback(query, user_id, data)
    
    async def handle_script_callback(self, query, user_id: int, data: str):
        """Handle script-related callbacks"""
        if data == 'script_new':
            await query.edit_message_text(
                "📝 *Create New Script*\n\n"
                "Please enter a name for your script:",
                parse_mode='Markdown'
            )
            user_sessions[user_id] = {'state': 'waiting_for_script_name'}
        
        elif data.startswith('script_view_'):
            script_id = int(data.split('_')[2])
            script = db.get_script(user_id, script_id)
            
            if script:
                script_info = f"""
📝 *Your Script: {script['name']}*

📁 Opening Audio: {'✅ Uploaded' if script['opening_audio_path'] else '❌ Not uploaded'}
📁 After Digit Audio: {'✅ Uploaded' if script['after_digit_audio_path'] else '❌ Not uploaded'}
                """
                
                keyboard = [
                    [InlineKeyboardButton("🎵 Update Opening Audio", callback_data=f"script_update_opening_{script_id}")],
                    [InlineKeyboardButton("🎵 Update After Digit Audio", callback_data=f"script_update_after_{script_id}")],
                    [InlineKeyboardButton("🔙 Back", callback_data="script_back")]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(script_info, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await query.edit_message_text("❌ Script not found or you don't have permission to view it.")
        
        elif data.startswith('script_update_opening_'):
            script_id = int(data.split('_')[3])
            # Verify user owns this script
            script = db.get_script(user_id, script_id)
            if script:
                await query.edit_message_text(
                    "🎵 *Update Opening Audio*\n\n"
                    "Please upload the new opening audio file (MP3):",
                    parse_mode='Markdown'
                )
                user_sessions[user_id] = {
                    'state': 'waiting_for_opening_audio', 
                    'script_id': script_id,
                    'updating': True
                }
            else:
                await query.edit_message_text("❌ Script not found or you don't have permission to edit it.")
        
        elif data.startswith('script_update_after_'):
            script_id = int(data.split('_')[3])
            # Verify user owns this script
            script = db.get_script(user_id, script_id)
            if script:
                await query.edit_message_text(
                    "🎵 *Update After Digit Audio*\n\n"
                    "Please upload the new after-digit audio file (MP3):",
                    parse_mode='Markdown'
                )
                user_sessions[user_id] = {
                    'state': 'waiting_for_after_digit_audio', 
                    'script_id': script_id,
                    'updating': True
                }
            else:
                await query.edit_message_text("❌ Script not found or you don't have permission to edit it.")
    
    async def handle_settings_callback(self, query, user_id: int, data: str):
        """Handle settings-related callbacks"""
        if data == 'settings_concurrent':
            await query.edit_message_text(
                "📞 *Set Concurrent Calls*\n\n"
                "Enter the maximum number of simultaneous calls (1-20):"
            )
            user_sessions[user_id] = {'state': 'waiting_for_concurrent_calls'}
        
        elif data == 'settings_rate':
            await query.edit_message_text(
                "⏱️ *Set Calls per Second*\n\n"
                "Enter the number of calls per second (0.1-10.0):"
            )
            user_sessions[user_id] = {'state': 'waiting_for_calls_per_second'}
        
        elif data == 'settings_caller_id':
            await query.edit_message_text(
                "📱 *Set Caller ID*\n\n"
                "Enter the phone number to display as caller ID (format: +1234567890):"
            )
            user_sessions[user_id] = {'state': 'waiting_for_caller_id'}
        
        elif data == 'settings_script':
            scripts = db.get_scripts(user_id)
            if not scripts:
                await query.edit_message_text(
                    "❌ No scripts available. Please create a script first using /script"
                )
                return
            
            keyboard = []
            for script in scripts:
                keyboard.append([InlineKeyboardButton(
                    script['name'], 
                    callback_data=f"set_active_script_{script['id']}"
                )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "📝 *Select Your Active Script*\n\nChoose which script to use for calls:",
                reply_markup=reply_markup
            )
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input based on user session state"""
        user_id = update.effective_user.id
        
        if user_id not in user_sessions:
            return
        
        session = user_sessions[user_id]
        state = session.get('state')
        text = update.message.text.strip()
        
        if state == 'waiting_for_script_name':
            session['script_name'] = text
            session['state'] = 'waiting_for_opening_audio'
            await update.message.reply_text(
                f"✅ Script name set to: {text}\n\n"
                "Now please upload the opening audio file (MP3):"
            )
        
        elif state == 'waiting_for_concurrent_calls':
            try:
                concurrent_calls = int(text)
                if 1 <= concurrent_calls <= 20:
                    db.save_user_settings(user_id, concurrent_calls=concurrent_calls)
                    await update.message.reply_text(f"✅ Concurrent calls set to: {concurrent_calls}")
                    del user_sessions[user_id]
                else:
                    await update.message.reply_text("❌ Please enter a number between 1 and 20.")
            except ValueError:
                await update.message.reply_text("❌ Please enter a valid number.")
        
        elif state == 'waiting_for_calls_per_second':
            try:
                calls_per_second = float(text)
                if 0.1 <= calls_per_second <= 10.0:
                    db.save_user_settings(user_id, calls_per_second=calls_per_second)
                    await update.message.reply_text(f"✅ Calls per second set to: {calls_per_second}")
                    del user_sessions[user_id]
                else:
                    await update.message.reply_text("❌ Please enter a number between 0.1 and 10.0.")
            except ValueError:
                await update.message.reply_text("❌ Please enter a valid number.")
        
        elif state == 'waiting_for_caller_id':
            # Basic phone number validation
            if text.startswith('+') and len(text) >= 10:
                db.save_user_settings(user_id, caller_id=text)
                await update.message.reply_text(f"✅ Caller ID set to: {text}")
                del user_sessions[user_id]
            else:
                await update.message.reply_text("❌ Please enter a valid phone number (format: +1234567890).")

def main():
    """Main function"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
    
    # Create application
    application = Application.builder().token(token).build()
    
    bot = CallBot()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("call", bot.call_command))
    application.add_handler(CommandHandler("recall", bot.recall_command))
    application.add_handler(CommandHandler("script", bot.script_command))
    application.add_handler(CommandHandler("settings", bot.settings_command))
    
    # File and text handlers
    application.add_handler(MessageHandler(filters.Document.ALL, bot.handle_file))
    application.add_handler(MessageHandler(filters.AUDIO, bot.handle_file))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_text))
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Start the bot
    logger.info("Starting Call Campaign Bot...")
    application.run_polling()

if __name__ == '__main__':
    main() 