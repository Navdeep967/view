
import telebot
import asyncio
import threading
import os
from telebot import types
from proxy_manager import proxy_manager, Proxy
# Import will be set when initialized
db = None
app = None
Proxy = None

def init_telegram_bot(database, flask_app, proxy_model):
    global db, app, Proxy
    db = database
    app = flask_app
    Proxy = proxy_model
import logging
from datetime import datetime

# Initialize bot - Replace with your actual values
BOT_TOKEN = '8023553474:AAG-VTLmG6Itdmay5sEG-VnaaOPfg14FFfA'  # Replace with your bot token
ADMIN_CHAT_ID = '6294868615'  # Replace with your chat ID

bot = telebot.TeleBot(BOT_TOKEN)

class TelegramProxyBot:
    def __init__(self):
        self.is_checking = False
        
    def setup_handlers(self):
        @bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                bot.reply_to(message, "❌ Unauthorized access. This bot is for admin use only.")
                return
            
            help_text = """
🤖 *Proxy Manager Bot*

*Commands:*
/status - Get proxy statistics
/check - Check all proxies manually
/working - Get list of working proxies
/failed - Get list of failed proxies
/clear_failed - Remove all failed proxies
/delete [days] - Delete old proxies and save working ones
/clear_all - Delete ALL proxies from database

*To add proxies:*
Send a .txt file with proxies (one per line)
Supported formats:
- ip:port
- http://ip:port
- socks4://ip:port
- socks5://ip:port

*Features:*
✅ Auto proxy checking every 5 hours
✅ Bulk proxy import (up to 50k)
✅ Real-time status updates
✅ Working proxy notifications
✅ Auto-save working proxies to file
            """
            bot.reply_to(message, help_text, parse_mode='Markdown')
        
        @bot.message_handler(commands=['status'])
        def get_status(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                return
            
            with app.app_context():
                total_proxies = Proxy.query.count()
                working_proxies = Proxy.query.filter_by(is_working=True).count()
                failed_proxies = Proxy.query.filter_by(is_working=False).count()
                
                success_rate = (working_proxies/total_proxies*100) if total_proxies > 0 else 0
                
                status_text = f"""
📊 *Proxy Status Report*

📈 *Statistics:*
• Total Proxies: {total_proxies}
• Working: {working_proxies} ✅
• Failed: {failed_proxies} ❌
• Success Rate: {success_rate:.1f}%
• Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔄 *Auto Checker:* {'Running' if not self.is_checking else 'In Progress'}
                """
                bot.reply_to(message, status_text, parse_mode='Markdown')
        
        @bot.message_handler(commands=['check'])
        def manual_check(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                return
            
            if self.is_checking:
                bot.reply_to(message, "⏳ Proxy check already in progress...")
                return
            
            bot.reply_to(message, "🔄 Starting manual proxy check...")
            threading.Thread(target=self.check_proxies_async, args=(message.chat.id,)).start()
        
        @bot.message_handler(commands=['working'])
        def get_working_proxies(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                return
            
            with app.app_context():
                working_proxies = Proxy.query.filter_by(is_working=True).order_by(Proxy.response_time.asc()).limit(20).all()
                
                if not working_proxies:
                    bot.reply_to(message, "❌ No working proxies found!")
                    return
                
                proxy_text = "✅ *Top 20 Working Proxies:*\n\n"
                for i, proxy in enumerate(working_proxies, 1):
                    proxy_text += f"{i}. `{proxy.proxy_string}` ({proxy.proxy_type})\n"
                    proxy_text += f"   ⚡ {proxy.response_time:.2f}s | 📊 {proxy.success_rate:.1f}%\n\n"
                
                bot.reply_to(message, proxy_text, parse_mode='Markdown')
        
        @bot.message_handler(commands=['failed'])
        def get_failed_proxies(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                return
            
            with app.app_context():
                failed_proxies = Proxy.query.filter_by(is_working=False).limit(10).all()
                
                if not failed_proxies:
                    bot.reply_to(message, "✅ No failed proxies!")
                    return
                
                proxy_text = "❌ *Recent Failed Proxies:*\n\n"
                for i, proxy in enumerate(failed_proxies, 1):
                    proxy_text += f"{i}. `{proxy.proxy_string}` ({proxy.proxy_type})\n"
                    proxy_text += f"   📊 {proxy.success_rate:.1f}% success rate\n\n"
                
                bot.reply_to(message, proxy_text, parse_mode='Markdown')
        
        @bot.message_handler(commands=['clear_failed'])
        def clear_failed_proxies(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                return
            
            with app.app_context():
                failed_count = Proxy.query.filter_by(is_working=False).count()
                Proxy.query.filter_by(is_working=False).delete()
                db.session.commit()
                
                bot.reply_to(message, f"🗑️ Removed {failed_count} failed proxies!")
        
        @bot.message_handler(commands=['clear_all'])
        def clear_all_proxies(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                return
            
            try:
                with app.app_context():
                    total_count = Proxy.query.count()
                    
                    # Delete all proxies
                    Proxy.query.delete()
                    db.session.commit()
                    
                    result_text = f"""
🗑️ *All Proxies Deleted*

📊 *Results:*
• Deleted: {total_count} proxies
• Database cleared completely
• Ready for new proxy imports

✅ You can now add new proxies by sending a .txt file to the bot
                    """
                    bot.reply_to(message, result_text, parse_mode='Markdown')
                    
            except Exception as e:
                bot.reply_to(message, f"❌ Error deleting all proxies: {str(e)}")
        
        @bot.message_handler(commands=['delete'])
        def delete_old_proxies(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                return
            
            # Parse command for time parameter (default 7 days)
            try:
                command_parts = message.text.split()
                days = 7  # default
                if len(command_parts) > 1:
                    days = int(command_parts[1])
                
                with app.app_context():
                    from datetime import datetime, timedelta
                    cutoff_date = datetime.utcnow() - timedelta(days=days)
                    
                    # First, save working proxies to file
                    working_proxies = Proxy.query.filter_by(is_working=True).all()
                    with open('workingproxy.txt', 'w') as f:
                        for proxy in working_proxies:
                            f.write(f"{proxy.proxy_string}\n")
                    
                    # Delete old proxies (both working and failed)
                    old_proxies = Proxy.query.filter(Proxy.last_checked < cutoff_date).all()
                    deleted_count = len(old_proxies)
                    
                    for proxy in old_proxies:
                        db.session.delete(proxy)
                    
                    db.session.commit()
                    
                    result_text = f"""
🗑️ *Old Proxy Cleanup Complete*

📊 *Results:*
• Deleted: {deleted_count} old proxies
• Older than: {days} days
• Working proxies saved to: workingproxy.txt
• Remaining proxies: {Proxy.query.count()}

✅ *File created:* workingproxy.txt with {len(working_proxies)} working proxies
                    """
                    bot.reply_to(message, result_text, parse_mode='Markdown')
                    
            except ValueError:
                bot.reply_to(message, "❌ Invalid number. Usage: /delete [days]\nExample: /delete 7 (deletes proxies older than 7 days)")
            except Exception as e:
                bot.reply_to(message, f"❌ Error deleting old proxies: {str(e)}")
        
        @bot.message_handler(content_types=['document'])
        def handle_proxy_file(message):
            if str(message.chat.id) != ADMIN_CHAT_ID:
                bot.reply_to(message, "❌ Unauthorized access.")
                return
            
            if not message.document.file_name.endswith('.txt'):
                bot.reply_to(message, "❌ Please send a .txt file containing proxies.")
                return
            
            try:
                # Download file
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                
                # Process file content
                text_content = downloaded_file.decode('utf-8')
                
                bot.reply_to(message, "📥 Processing proxy file...")
                
                with app.app_context():
                    result = proxy_manager.add_proxies_from_text(text_content)
                
                if 'error' in result:
                    bot.reply_to(message, f"❌ Error processing file: {result['error']}")
                    return
                
                result_text = f"""
📊 *Proxy Import Results:*

✅ Added: {result['added']}
❌ Failed: {result['failed']}
🔄 Duplicates: {result['duplicates']}
📝 Total Processed: {result['total_processed']}

🔄 Starting automatic proxy check...
                """
                bot.reply_to(message, result_text)
                
                # Start automatic check
                if result['added'] > 0:
                    threading.Thread(target=self.check_proxies_async, args=(message.chat.id,)).start()
                
            except Exception as e:
                bot.reply_to(message, f"❌ Error processing file: {str(e)}")
    
    def check_proxies_async(self, chat_id):
        """Run proxy check in async context"""
        try:
            self.is_checking = True
            bot.send_message(chat_id, "🔄 Checking proxies... This may take a while.")
            
            # Run async function in thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            with app.app_context():
                loop.run_until_complete(proxy_manager.update_proxy_status())
            
            # Send results
            with app.app_context():
                total_proxies = Proxy.query.count()
                working_proxies = Proxy.query.filter_by(is_working=True).count()
                
                success_rate = (working_proxies/total_proxies*100) if total_proxies > 0 else 0
                
                result_text = f"""
✅ *Proxy Check Complete!*

📊 Results:
• Total Proxies: {total_proxies}
• Working: {working_proxies}
• Success Rate: {success_rate:.1f}%

⏰ Completed at: {datetime.now().strftime('%H:%M:%S')}
                """
                bot.send_message(chat_id, result_text)
                
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error during proxy check: {str(e)}")
        finally:
            self.is_checking = False
    
    def send_notification(self, message):
        """Send notification to admin"""
        try:
            bot.send_message(ADMIN_CHAT_ID, message, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Failed to send Telegram notification: {e}")
    
    def start_bot(self):
        """Start the bot with conflict prevention"""
        self.setup_handlers()
        
        try:
            # Stop any existing webhook and clear pending updates
            bot.remove_webhook()
            bot.delete_webhook(drop_pending_updates=True)
            
            # Clear any pending updates
            try:
                bot.get_updates(offset=-1, timeout=1)
            except:
                pass
                
            bot.send_message(ADMIN_CHAT_ID, "🤖 *Proxy Manager Bot Started!*\n\nReady to manage your proxies.", parse_mode='Markdown')
        except Exception as e:
            print(f"Warning: Could not send startup message: {e}")
        
        # Use polling with restart capability
        while True:
            try:
                print("🔄 Starting Telegram bot polling...")
                bot.infinity_polling(none_stop=True, timeout=30, long_polling_timeout=30)
            except Exception as e:
                print(f"Bot polling error: {e}")
                if "409" in str(e) or "Conflict" in str(e):
                    print("⚠️  Bot conflict detected, waiting 60 seconds before retry...")
                    import time
                    time.sleep(60)
                    # Clear pending updates and try again
                    try:
                        bot.delete_webhook(drop_pending_updates=True)
                        bot.get_updates(offset=-1, timeout=1)
                    except:
                        pass
                else:
                    print("🔄 Restarting bot in 10 seconds...")
                    import time
                    time.sleep(10)

# Global bot instance
telegram_bot = TelegramProxyBot()
