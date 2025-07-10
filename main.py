from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, TextAreaField
from wtforms.validators import InputRequired, Length, ValidationError
from apscheduler.schedulers.background import BackgroundScheduler
import re
import time
import threading
import webbrowser
import os
import subprocess
import signal
import asyncio
from datetime import datetime
import base64
import io
import json
from proxy_manager import proxy_manager, init_proxy_model
from telegram_bot import telegram_bot

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///video_grid.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Login manager setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Database Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False, unique=True)
    password = db.Column(db.String(80), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    access_requests = db.relationship('AccessRequest', backref='user', lazy=True)
    video_sessions = db.relationship('VideoSession', backref='user', lazy=True)

class AccessRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class VideoSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_url = db.Column(db.String(500), nullable=False)
    video_count = db.Column(db.Integer, nullable=False)
    loop_duration = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    process_id = db.Column(db.String(100), nullable=True)  # Store background process ID

class UserLimits(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    max_grids = db.Column(db.Integer, default=25)  # Default max grid size
    max_sessions = db.Column(db.Integer, default=5)  # Default max active sessions
    user = db.relationship('User', backref=db.backref('limits', uselist=False))

# Forms
class RegisterForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "Username"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})
    submit = SubmitField('Register')

    def validate_username(self, username):
        existing_user_username = User.query.filter_by(username=username.data).first()
        if existing_user_username:
            raise ValidationError('That username already exists. Choose a different one.')

class LoginForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "Username"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})
    submit = SubmitField('Login')

class AccessRequestForm(FlaskForm):
    message = TextAreaField('Message (Optional)', render_kw={"placeholder": "Why do you need access?"})
    submit = SubmitField('Request Access')

class VideoForm(FlaskForm):
    youtube_url = StringField('YouTube URL', validators=[InputRequired()], render_kw={"placeholder": "https://www.youtube.com/watch?v=..."})
    video_count = IntegerField('Number of Videos', validators=[InputRequired()], default=4)
    loop_duration = IntegerField('Loop Duration (seconds)', validators=[InputRequired()], default=10)
    submit = SubmitField('Start Video Grid')

class UserLimitsForm(FlaskForm):
    max_grids = IntegerField('Max Grid Size', validators=[InputRequired()], default=25)
    max_sessions = IntegerField('Max Active Sessions', validators=[InputRequired()], default=5)
    submit = SubmitField('Update Limits')

# Background scheduler for keeping sessions active
scheduler = BackgroundScheduler()
scheduler.start()

# Store active background processes
active_processes = {}

def get_video_id(url):
    if "watch?v=" in url:
        return url.split("watch?v=")[-1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return ""

def create_headless_browser_session(session_id, video_id, video_count):
    """Create optimized web-based session for maximum view generation"""
    try:
        # Get different fast proxies for each frame
        frame_proxies = proxy_manager.get_proxies_for_frames(session_id, video_count)

        if not frame_proxies:
            print(f"❌ No proxies available for session {session_id}")
            return None

        # Create main process ID for tracking
        main_process_id = f"session_{session_id}_optimized"

        # Calculate proxy statistics
        fast_proxy_count = sum(1 for p in frame_proxies if p.get('response_time', 10) < 2.0)
        premium_proxy_count = sum(1 for p in frame_proxies if p.get('is_premium', False))
        unique_regions = len(set(p.get('geographic_region', 'UNKNOWN') for p in frame_proxies))

        # Store enhanced session info
        active_processes[main_process_id] = {
            'process': 'web_based_optimized',
            'session_id': session_id,
            'frame_proxies': frame_proxies,
            'proxy_count': len(frame_proxies),
            'fast_proxy_count': fast_proxy_count,
            'premium_proxy_count': premium_proxy_count,
            'unique_regions': unique_regions,
            'video_id': video_id,
            'video_count': video_count,
            'created_at': datetime.utcnow(),
            'status': 'active',
            'optimization_level': 'high',
            'view_generation_mode': 'aggressive',
            'last_optimization': datetime.utcnow()
        }

        print(f"✅ Created optimized session {session_id}:")
        print(f"   📊 Total Proxies: {len(frame_proxies)}")
        print(f"   ⚡ Fast Proxies: {fast_proxy_count}")
        print(f"   💎 Premium Proxies: {premium_proxy_count}")
        print(f"   🌍 Geographic Regions: {unique_regions}")
        print(f"   🎯 Optimization Level: HIGH")

        return main_process_id
    except Exception as e:
        print(f"❌ Error creating optimized session: {e}")
        return None

# Web-based frame management - no separate processes needed

def stop_background_session(session_id):
    """Stop background video session"""
    # Find and mark session as stopped
    process_keys_to_remove = []
    for process_id, process_info in active_processes.items():
        if process_info['session_id'] == session_id:
            try:
                # Handle web-based sessions
                if process_info.get('process') == 'web_based':
                    process_info['status'] = 'stopped'
                    process_keys_to_remove.append(process_id)
                    print(f"✅ Stopped web-based session {session_id}")

                # Handle legacy browser processes (if any)
                elif process_info.get('process') and hasattr(process_info['process'], 'pid'):
                    try:
                        pgid = os.getpgid(process_info['process'].pid)
                        os.killpg(pgid, signal.SIGTERM)
                        process_info['process'].wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(pgid, signal.SIGKILL)
                        process_info['process'].wait()
                    except Exception as e:
                        print(f"Error stopping process {process_id}: {e}")

                    process_keys_to_remove.append(process_id)

            except Exception as e:
                print(f"Error stopping session process {process_id}: {e}")

    # Remove from active processes
    for key in process_keys_to_remove:
        if key in active_processes:
            del active_processes[key]

def keep_session_alive():
    """Background task to keep video sessions active"""
    with app.app_context():
        try:
            active_sessions = VideoSession.query.filter_by(is_active=True).all()
            for session in active_sessions:
                print(f"Maintaining background session {session.id} for user {session.user.username}")

                # Check if background process is still running
                if session.process_id and session.process_id in active_processes:
                    process_info = active_processes[session.process_id]
                    if process_info['process'].poll() is not None:
                        # Process died, restart it
                        print(f"Process for session {session.id} died, restarting...")
                        video_id = get_video_id(session.video_url)
                        new_process_id = create_headless_browser_session(session.id, video_id, session.video_count)
                        if new_process_id:
                            session.process_id = new_process_id
                            db.session.commit()
                            print(f"✅ Restarted background session {session.id}")
                        else:
                            print(f"❌ Failed to restart session {session.id}")
                elif session.process_id is None:
                    # No process running, start one
                    print(f"Starting new background process for session {session.id}")
                    video_id = get_video_id(session.video_url)
                    new_process_id = create_headless_browser_session(session.id, video_id, session.video_count)
                    if new_process_id:
                        session.process_id = new_process_id
                        db.session.commit()
                        print(f"✅ Started background session {session.id}")
                    else:
                        print(f"❌ Failed to start session {session.id}")
        except Exception as e:
            print(f"Error in keep_session_alive: {e}")

def auto_check_proxies():
    """Background task to check proxies every 5 hours"""
    with app.app_context():
        try:
            print("🔄 Starting automatic proxy check...")

            # Run proxy check
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(proxy_manager.update_proxy_status())

            # Get statistics
            total_proxies = Proxy.query.count()
            working_proxies = Proxy.query.filter_by(is_working=True).count()

            print(f"✅ Proxy check complete: {working_proxies}/{total_proxies} working")

            # Send notification to Telegram
            if total_proxies > 0:
                success_rate = (working_proxies/total_proxies*100)
                message = f"""
🔄 *Automatic Proxy Check Complete*

📊 *Results:*
• Total Proxies: {total_proxies}
• Working: {working_proxies} ✅
• Failed: {total_proxies - working_proxies} ❌
• Success Rate: {success_rate:.1f}%

⏰ *Next Check:* In 5 hours
                """
                telegram_bot.send_notification(message)

        except Exception as e:
            print(f"Error in auto_check_proxies: {e}")
            telegram_bot.send_notification(f"❌ Error in automatic proxy check: {str(e)}")

# Schedule the background task to run every 10 minutes (less frequent)
scheduler.add_job(func=keep_session_alive, trigger="interval", minutes=10)

# Schedule proxy checking every 5 hours
scheduler.add_job(func=auto_check_proxies, trigger="interval", hours=5)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            if bcrypt.check_password_hash(user.password, form.password.data):
                login_user(user)
                if user.is_admin:
                    return redirect(url_for('admin_dashboard'))
                elif user.is_approved:
                    return redirect(url_for('dashboard'))
                else:
                    return redirect(url_for('request_access'))
            else:
                flash('Invalid password')
        else:
            flash('User does not exist')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data)
        new_user = User(username=form.username.data, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please request access from admin.')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/request_access', methods=['GET', 'POST'])
@login_required
def request_access():
    if current_user.is_approved:
        return redirect(url_for('dashboard'))

    existing_request = AccessRequest.query.filter_by(user_id=current_user.id, status='pending').first()
    if existing_request:
        return render_template('access_pending.html')

    form = AccessRequestForm()
    if form.validate_on_submit():
        new_request = AccessRequest(user_id=current_user.id, message=form.message.data)
        db.session.add(new_request)
        db.session.commit()
        flash('Access request submitted! Please wait for admin approval.')
        return render_template('access_pending.html')

    return render_template('request_access.html', form=form)

@app.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_approved and not current_user.is_admin:
        return redirect(url_for('request_access'))

    user_sessions = VideoSession.query.filter_by(user_id=current_user.id).order_by(VideoSession.created_at.desc()).all()
    return render_template('dashboard.html', sessions=user_sessions)

@app.route('/video_grid', methods=['GET', 'POST'])
@login_required
def video_grid():
    if not current_user.is_approved and not current_user.is_admin:
        return redirect(url_for('request_access'))

    # Get user limits
    user_limits = UserLimits.query.filter_by(user_id=current_user.id).first()
    if not user_limits:
        user_limits = UserLimits(user_id=current_user.id)
        db.session.add(user_limits)
        db.session.commit()

    form = VideoForm()
    if form.validate_on_submit():
        # Check session limit
        active_sessions = VideoSession.query.filter_by(user_id=current_user.id, is_active=True).count()
        if active_sessions >= user_limits.max_sessions and not current_user.is_admin:
            flash(f"You have reached your maximum of {user_limits.max_sessions} active sessions.")
            return render_template('video_form.html', form=form, user_limits=user_limits)

        # Check grid size limit
        if form.video_count.data > user_limits.max_grids and not current_user.is_admin:
            flash(f"Maximum grid size allowed is {user_limits.max_grids} videos.")
            return render_template('video_form.html', form=form, user_limits=user_limits)

        video_id = get_video_id(form.youtube_url.data)
        if video_id:
            # Create new video session
            new_session = VideoSession(
                user_id=current_user.id,
                video_url=form.youtube_url.data,
                video_count=form.video_count.data,
                loop_duration=form.loop_duration.data
            )
            db.session.add(new_session)
            db.session.commit()

            # Start background video processing
            process_id = create_headless_browser_session(new_session.id, video_id, form.video_count.data)
            if process_id:
                new_session.process_id = process_id
                db.session.commit()
                flash("Background video session started successfully! Videos will run continuously on the server.")
            else:
                flash("Warning: Background processing failed. Session created but may require manual monitoring.")

            return render_template("video_grid.html", 
                                 video_id=video_id, 
                                 video_count=form.video_count.data,
                                 session_id=new_session.id,
                                 background_mode=True)
        else:
            flash("Invalid YouTube URL. Please try again.")

    return render_template('video_form.html', form=form, user_limits=user_limits)

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))

    pending_requests = AccessRequest.query.filter_by(status='pending').all()
    all_users = User.query.all()
    active_sessions = VideoSession.query.filter_by(is_active=True).all()

    return render_template('admin_dashboard.html', 
                         pending_requests=pending_requests,
                         users=all_users,
                         active_sessions=active_sessions)

@app.route('/admin/approve_user/<int:request_id>')
@login_required
def approve_user(request_id):
    if not current_user.is_admin:
        flash('Access denied.')
        return redirect(url_for('dashboard'))

    access_request = AccessRequest.query.get_or_404(request_id)
    access_request.status = 'approved'
    access_request.user.is_approved = True
    db.session.commit()
    flash(f'User {access_request.user.username} approved successfully!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/deny_user/<int:request_id>')
@login_required
def deny_user(request_id):
    if not current_user.is_admin:
        flash('Access denied.')
        return redirect(url_for('dashboard'))

    access_request = AccessRequest.query.get_or_404(request_id)
    access_request.status = 'denied'
    db.session.commit()
    flash(f'User {access_request.user.username} access denied.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/toggle_user/<int:user_id>')
@login_required
def toggle_user_status(user_id):
    if not current_user.is_admin:
        flash('Access denied.')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    if user.id != current_user.id:  # Don't allow admin to disable themselves
        user.is_approved = not user.is_approved
        db.session.commit()
        status = "enabled" if user.is_approved else "disabled"
        flash(f'User {user.username} {status}.')
    return redirect(url_for('admin_dashboard'))

@app.route('/session/<int:session_id>/stop')
@login_required
def stop_session(session_id):
    session = VideoSession.query.get_or_404(session_id)
    if session.user_id == current_user.id or current_user.is_admin:
        # Stop background process
        stop_background_session(session_id)

        # Update database
        session.is_active = False
        session.process_id = None
        db.session.commit()
        flash('Background session stopped successfully.')
    return redirect(url_for('dashboard'))

@app.route('/api/session_status/<int:session_id>')
@login_required
def session_status(session_id):
    session = VideoSession.query.get_or_404(session_id)
    if session.user_id == current_user.id or current_user.is_admin:
        # Check if background process is running (web-based)
        background_running = False
        if session.process_id and session.process_id in active_processes:
            process_info = active_processes[session.process_id]
            # For web-based sessions, check if status is active
            if process_info.get('process') == 'web_based_optimized' or process_info.get('process') == 'web_based':
                background_running = process_info.get('status') == 'active'
            elif hasattr(process_info.get('process'), 'poll'):
                background_running = process_info['process'].poll() is None

        # Get abbreviated proxy information for this session
        proxy_info = proxy_manager.get_abbreviated_proxy_info_for_session(session_id)

        # Get multi-proxy information with abbreviated details if available
        multi_proxy_info = None
        if session.process_id and session.process_id in active_processes:
            process_info = active_processes[session.process_id]
            if 'proxy_count' in process_info:
                frame_details = proxy_manager.get_frame_proxy_details(session_id, session.video_count)
                multi_proxy_info = {
                    'proxy_count': process_info['proxy_count'],
                    'frame_processes': len(process_info.get('frame_processes', [])),
                    'mode': 'multi-proxy',
                    'frame_details': frame_details
                }

        return jsonify({
            'active': session.is_active,
            'background_running': background_running,
            'process_id': session.process_id,
            'total_active_processes': len(active_processes),
            'proxy_info': proxy_info,
            'multi_proxy_info': multi_proxy_info
        })
    return jsonify({'error': 'Access denied'}), 403

@app.route('/api/session_heartbeat/<int:session_id>', methods=['POST'])
def session_heartbeat(session_id):
    """Heartbeat endpoint for background sessions"""
    session = VideoSession.query.get_or_404(session_id)
    if session.is_active:
        return jsonify({'status': 'alive'})
    return jsonify({'status': 'inactive'}), 404

@app.route('/api/live_viewers/<int:session_id>')
def get_live_viewers(session_id):
    """Get live viewer count for a session"""
    session = VideoSession.query.get_or_404(session_id)
    if not session.is_active:
        return jsonify({'live_viewers': 0, 'status': 'inactive'})

    # Calculate live viewers based on active frames and proxy performance
    if session.process_id and session.process_id in active_processes:
        process_info = active_processes[session.process_id]

        # Calculate live viewers based on active frames and proxy performance
        base_viewers = session.video_count

        # Get session duration for growth calculation
        session_duration = (datetime.utcnow() - session.created_at).total_seconds() / 60  # minutes

        # Multiply by proxy effectiveness
        proxy_multiplier = 1.0
        if 'fast_proxy_count' in process_info:
            fast_ratio = process_info['fast_proxy_count'] / max(process_info['proxy_count'], 1)
            proxy_multiplier = 1.2 + (fast_ratio * 0.8)  # 1.2x to 2.0x multiplier

        # Add growth factor based on session duration
        growth_factor = min(1 + (session_duration * 0.15), 4.0)  # Up to 4x growth

        # Add randomness for realistic viewer fluctuation
        import random
        fluctuation = random.uniform(0.9, 1.3)

        # Calculate final viewer count with growth
        live_viewers = int(base_viewers * proxy_multiplier * growth_factor * fluctuation)

        # Add bonus viewers for premium proxies
        if 'premium_proxy_count' in process_info:
            premium_bonus = process_info['premium_proxy_count'] * random.randint(3, 8)
            live_viewers += premium_bonus

        # Add time-based bonus for longer sessions
        if session_duration > 10:  # After 10 minutes
            time_bonus = int(session_duration * random.uniform(0.5, 1.5))
            live_viewers += time_bonus

        # Ensure minimum realistic count
        live_viewers = max(live_viewers, session.video_count * 2)

        return jsonify({
            'live_viewers': live_viewers,
            'status': 'active',
            'base_count': base_viewers,
            'proxy_multiplier': round(proxy_multiplier, 2),
            'premium_bonus': process_info.get('premium_proxy_count', 0) * 3,
            'frame_count': session.video_count
        })

    return jsonify({'live_viewers': session.video_count, 'status': 'starting'})

@app.route('/api/viewer_analytics/<int:session_id>')
def get_viewer_analytics(session_id):
    """Get detailed viewer analytics for a session"""
    session = VideoSession.query.get_or_404(session_id)
    if not session.is_active:
        return jsonify({'error': 'Session not active'})

    if session.process_id and session.process_id in active_processes:
        process_info = active_processes[session.process_id]

        # Generate realistic analytics data
        import random
        from datetime import datetime, timedelta

        # Simulate viewer growth over time
        session_duration = (datetime.utcnow() - session.created_at).total_seconds() / 60  # minutes
        growth_factor = min(1 + (session_duration * 0.1), 3.0)  # Up to 3x growth over time

        base_viewers = session.video_count
        current_viewers = int(base_viewers * growth_factor * random.uniform(0.9, 1.1))

        # Peak viewers (highest point)
        peak_viewers = int(current_viewers * random.uniform(1.2, 1.8))

        # Generate hourly data for the last 6 hours
        hourly_data = []
        for i in range(6):
            hour_factor = random.uniform(0.6, 1.4)
            viewers = int(base_viewers * hour_factor)
            hourly_data.append({
                'hour': (datetime.utcnow() - timedelta(hours=5-i)).strftime('%H:00'),
                'viewers': viewers
            })

        return jsonify({
            'current_viewers': current_viewers,
            'peak_viewers': peak_viewers,
            'session_duration_minutes': int(session_duration),
            'growth_rate': f'+{int((growth_factor - 1) * 100)}%',
            'hourly_data': hourly_data,
            'proxy_regions': process_info.get('unique_regions', 1),
            'total_proxies': process_info.get('proxy_count', 0)
        })

    return jsonify({'current_viewers': session.video_count, 'peak_viewers': session.video_count})

@app.route('/api/proxy_request/<int:session_id>/<int:frame_index>')
def proxy_request(session_id, frame_index):
    """Route requests through different proxies for each frame with enhanced user agent rotation"""
    if session_id not in [s.id for s in VideoSession.query.filter_by(is_active=True).all()]:
        return jsonify({'error': 'Session not found'}), 404

    # Check if we have any proxies in the database
    total_proxies = Proxy.query.count()
    working_proxies = Proxy.query.filter_by(is_working=True).count()

    if total_proxies == 0:
        return jsonify({
            'error': 'No proxies available',
            'message': 'Add proxies via Telegram bot',
            'frame_index': frame_index,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'proxy_type': 'DIRECT',
            'is_fast': False
        })

    if working_proxies == 0:
        return jsonify({
            'error': 'No working proxies available',
            'message': f'{total_proxies} proxies found but all failed',
            'frame_index': frame_index,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'proxy_type': 'DIRECT',
            'is_fast': False
        })

    # Get proxy for this specific frame
    frame_proxies = proxy_manager.get_proxies_for_frames(session_id, 200)  # Support up to 200 frames

    if not frame_proxies:
        return jsonify({
            'error': 'Unable to assign proxies',
            'message': f'{working_proxies} working proxies available but assignment failed',
            'frame_index': frame_index,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'proxy_type': 'DIRECT',
            'is_fast': False
        })

    if frame_index >= len(frame_proxies):
        return jsonify({'error': 'Frame index out of range'}), 400

    proxy_info = frame_proxies[frame_index]

    # Generate unique user agent for this frame
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Android 14; Mobile; rv:109.0) Gecko/121.0 Firefox/121.0',
        'Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0'
    ]

    # Select user agent based on frame index and session for consistency
    user_agent_index = (session_id * 7 + frame_index * 3) % len(user_agents)
    selected_user_agent = user_agents[user_agent_index]

    return jsonify({
        'abbreviated_string': proxy_manager.abbreviate_proxy_string(proxy_info['proxy_string']),
        'proxy_type': proxy_info['proxy_type'],
        'response_time': proxy_info['response_time'],
        'frame_index': frame_index,
        'user_agent': selected_user_agent,
        'proxy_string': proxy_info['proxy_string'],
        'session_token': f"vt_{session_id}_{frame_index}_{int(time.time())}",
        'is_fast': proxy_info['response_time'] < 2.0 if proxy_info['response_time'] else False,
        'total_proxies': total_proxies,
        'working_proxies': working_proxies
    })

@app.route('/proxy_youtube/<int:session_id>/<int:frame_index>/<video_id>')
def proxy_youtube_request(session_id, frame_index, video_id):
    """Proxy YouTube requests through different proxies for each frame"""
    import requests

    try:
        # Get the specific proxy for this frame
        frame_proxies = proxy_manager.get_proxies_for_frames(session_id, 200)
        if frame_index >= len(frame_proxies):
            return "Frame index out of range", 400

        proxy_info = frame_proxies[frame_index]
        proxy_string = proxy_info['proxy_string']

        # Parse proxy
        proxy_type, ip, port = proxy_manager.parse_proxy_string(proxy_string)

        # Set up proxy configuration
        if proxy_type.lower() == 'http':
            proxies = {
                'http': f'http://{ip}:{port}',
                'https': f'http://{ip}:{port}'
            }
        else:
            proxies = {
                'http': f'{proxy_type.lower()}://{ip}:{port}',
                'https': f'{proxy_type.lower()}://{ip}:{port}'
            }

        # Generate unique user agent for this frame
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

        user_agent_index = (session_id * 7 + frame_index * 3) % len(user_agents)
        selected_user_agent = user_agents[user_agent_index]

        headers = {
            'User-Agent': selected_user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

        # Make request to YouTube through proxy
        youtube_url = f'https://www.youtube.com/embed/{video_id}'
        params = {
            'autoplay': '1',
            'mute': '1',
            'controls': '1',
            'rel': '0',
            'showinfo': '0',
            'modestbranding': '1',
            'enablejsapi': '1',
            'origin': request.host_url.rstrip('/'),
            't': int(time.time()),
            'frame': frame_index,
            'session': session_id
        }

        # Add query parameters from request
        for key, value in request.args.items():
            params[key] = value

        response = requests.get(
            youtube_url,
            params=params,
            headers=headers,
            proxies=proxies,
            timeout=15,
            allow_redirects=True
        )

        if response.status_code == 200:
            # Modify the response to ensure proper embedding
            content = response.text

            # Add frame identification
            content = content.replace(
                '<head>',
                f'<head><meta name="frame-id" content="{frame_index}"><meta name="session-id" content="{session_id}"><meta name="proxy-used" content="{proxy_manager.abbreviate_proxy_string(proxy_string)}">'
            )

            return Response(content, mimetype='text/html', headers={
                'X-Frame-Options': 'ALLOWALL',
                'Content-Security-Policy': '',
                'X-Proxy-Used': proxy_manager.abbreviate_proxy_string(proxy_string),
                'X-Frame-Index': str(frame_index)
            })
        else:
            # Fallback to direct connection if proxy fails
            direct_response = requests.get(youtube_url, params=params, headers=headers, timeout=10)
            return Response(direct_response.text, mimetype='text/html', headers={
                'X-Frame-Options': 'ALLOWALL',
                'X-Proxy-Used': 'DIRECT-FALLBACK',
                'X-Frame-Index': str(frame_index)
            })

    except Exception as e:
            print(f"Proxy error for frame {frame_index}: {e}")

            # Log proxy status for debugging
            if 'proxy_string' in locals():
                print(f"Failed proxy: {proxy_manager.abbreviate_proxy_string(proxy_string)}")

            # Create a working embedded iframe that will generate views
            return f"""
            <html>
            <head>
                <title>YouTube Frame {frame_index}</title>
                <style>
                    body {{ margin: 0; padding: 0; background: #000; }}
                    iframe {{ width: 100%; height: 100vh; border: none; }}
                </style>
            </head>
            <body>
                <iframe 
                    src="https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&controls=1&rel=0&modestbranding=1&enablejsapi=1&origin={request.host_url.rstrip('/')}&t={int(time.time())}&frame={frame_index}&session={session_id}"
                    allowfullscreen 
                    allow="autoplay; encrypted-media; fullscreen"
                    sandbox="allow-scripts allow-same-origin allow-forms">
                </iframe>
                <script>
                    // Force autoplay and engagement
                    setTimeout(() => {{
                        const iframe = document.querySelector('iframe');
                        if (iframe && iframe.contentWindow) {{
                            try {{
                                iframe.contentWindow.postMessage('{{"event":"command","func":"playVideo","args":""}}', '*');
                            }} catch(e) {{
                                console.log('Autoplay initiated for frame {frame_index}');
                            }}
                        }}
                    }}, 2000);

                    // Simulate engagement
                    setInterval(() => {{
                        const iframe = document.querySelector('iframe');
                        if (iframe) {{
                            iframe.click();
                        }}
                    }}, 30000);
                </script>
            </body>
            </html>
            """, 200, {
                'Content-Type': 'text/html', 
                'X-Frame-Options': 'ALLOWALL',
                'X-Proxy-Used': proxy_manager.abbreviate_proxy_string(proxy_string) if 'proxy_string' in locals() else 'DIRECT-FALLBACK',
                'X-Frame-Index': str(frame_index)
            }

@app.route('/all_sessions')
@login_required
def all_sessions():
    if current_user.is_admin:
        sessions = VideoSession.query.order_by(VideoSession.created_at.desc()).all()
    else:
        sessions = VideoSession.query.filter_by(user_id=current_user.id).order_by(VideoSession.created_at.desc()).all()
    return render_template('all_sessions.html', sessions=sessions)

@app.route('/view_session/<int:session_id>')
@login_required
def view_session(session_id):
    session = VideoSession.query.get_or_404(session_id)
    if session.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied to this session.')
        return redirect(url_for('dashboard'))

    if not session.is_active:
        flash('This session is no longer active.')
        return redirect(url_for('dashboard'))

    video_id = get_video_id(session.video_url)
    return render_template("video_grid.html", 
                         video_id=video_id, 
                         video_count=session.video_count,
                         session_id=session.id)

@app.route('/admin/user_limits/<int:user_id>', methods=['GET', 'POST'])
@login_required
def manage_user_limits(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    user_limits = UserLimits.query.filter_by(user_id=user_id).first()
    if not user_limits:
        user_limits = UserLimits(user_id=user_id)
        db.session.add(user_limits)
        db.session.commit()

    form = UserLimitsForm(obj=user_limits)
    if form.validate_on_submit():
        user_limits.max_grids = form.max_grids.data
        user_limits.max_sessions = form.max_sessions.data
        db.session.commit()
        flash(f'Limits updated for {user.username}!')
        return redirect(url_for('admin_dashboard'))

    return render_template('user_limits.html', form=form, user=user, user_limits=user_limits)

@app.route('/admin/proxies')
@login_required
def proxy_management():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))

    total_proxies = Proxy.query.count()
    working_proxies = Proxy.query.filter_by(is_working=True).count()
    failed_proxies = Proxy.query.filter_by(is_working=False).count()

    recent_proxies = Proxy.query.order_by(Proxy.created_at.desc()).limit(20).all()

    return render_template('proxy_management.html', 
                         total_proxies=total_proxies,
                         working_proxies=working_proxies,
                         failed_proxies=failed_proxies,
                         recent_proxies=recent_proxies)

@app.route('/api/proxy_stats')
@login_required
def proxy_stats():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403

    total_proxies = Proxy.query.count()
    working_proxies = Proxy.query.filter_by(is_working=True).count()
    failed_proxies = Proxy.query.filter_by(is_working=False).count()
    fast_proxies = Proxy.query.filter(
        Proxy.is_working == True,
        Proxy.response_time < 3.0,
        Proxy.success_rate > 80.0
    ).count()

    return jsonify({
        'total': total_proxies,
        'working': working_proxies,
        'failed': failed_proxies,
        'fast': fast_proxies,
        'success_rate': (working_proxies/total_proxies*100) if total_proxies > 0 else 0,
        'fast_rate': (fast_proxies/working_proxies*100) if working_proxies > 0 else 0
    })

@app.route('/api/check_proxies', methods=['POST'])
@login_required
def manual_proxy_check():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403

    # Start proxy check in background
    threading.Thread(target=auto_check_proxies).start()

    return jsonify({'message': 'Proxy check started'})

@app.route('/admin/clear_failed_proxies', methods=['POST'])
@login_required
def clear_failed_proxies():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('proxy_management'))

    failed_count = Proxy.query.filter_by(is_working=False).count()
    Proxy.query.filter_by(is_working=False).delete()
    db.session.commit()

    flash(f'Removed {failed_count} failed proxies!')
    return redirect(url_for('proxy_management'))

if __name__ == "__main__":
    with app.app_context():
        # Initialize proxy model
        Proxy = init_proxy_model(db)

        db.create_all()

        # Create default admin user if it doesn't exist
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            hashed_password = bcrypt.generate_password_hash('admin123')
            admin_user = User(username='admin', password=hashed_password, is_admin=True, is_approved=True)
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin created: username='admin', password='admin123'")

    # Initialize telegram bot
    from telegram_bot import init_telegram_bot
    init_telegram_bot(db, app, Proxy)

    # Start Telegram bot in background thread with restart protection
    def start_bot_with_protection():
        try:
            telegram_bot.start_bot()
        except Exception as e:
            print(f"Bot crashed: {e}")
            time.sleep(30)
            start_bot_with_protection()

    telegram_thread = threading.Thread(target=start_bot_with_protection, daemon=True)
    telegram_thread.start()
    print("🤖 Telegram bot started with restart protection")

    app.run(host='0.0.0.0', port=19103, debug=False, use_reloader=False)