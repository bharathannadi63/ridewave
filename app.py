from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import csv
from io import StringIO
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import logging
import sys
import time
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Database configuration
try:
    if os.getenv('DATABASE_URL'):
        # Parse the DATABASE_URL
        db_url = os.getenv('DATABASE_URL')
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url
        logger.info(f"Using PostgreSQL database: {db_url}")
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ridewave.db'
        logger.info("Using SQLite database")
except Exception as e:
    logger.error(f"Error configuring database: {str(e)}")
    sys.exit(1)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database with connection pooling
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'max_overflow': 10,
    'pool_timeout': 30,
    'pool_recycle': 1800
}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    phone = db.Column(db.String(20))
    is_driver = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    rides = db.relationship('Ride', foreign_keys='Ride.user_id', backref='user', lazy=True)
    driver_rides = db.relationship('Ride', foreign_keys='Ride.driver_id', backref='driver', lazy=True)
    loyalty = db.relationship('UserLoyalty', backref='user', uselist=False)

class Bike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(200), nullable=False)
    engine = db.Column(db.String(50))
    power = db.Column(db.String(50))
    mileage = db.Column(db.String(50))
    type = db.Column(db.String(50))
    gallery_images = db.Column(db.JSON)
    is_available = db.Column(db.Boolean, default=True)
    min_kms = db.Column(db.Integer, nullable=False)

class LoyaltyTier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    min_points = db.Column(db.Integer, nullable=False)
    discount_percentage = db.Column(db.Float, nullable=False)

class UserLoyalty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    points = db.Column(db.Integer, default=0)
    tier_id = db.Column(db.Integer, db.ForeignKey('loyalty_tier.id'))
    tier = db.relationship('LoyaltyTier', backref='user_loyalties')
    
class Accessory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price_per_day = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(200))

class RideAccessory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ride_id = db.Column(db.Integer, db.ForeignKey('ride.id'), nullable=False)
    accessory_id = db.Column(db.Integer, db.ForeignKey('accessory.id'), nullable=False)

class Ride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pickup_location = db.Column(db.String(200), nullable=False)
    dropoff_location = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    bike_id = db.Column(db.Integer, db.ForeignKey('bike.id'), nullable=False)
    pickup_date = db.Column(db.DateTime, nullable=False)
    dropoff_date = db.Column(db.DateTime, nullable=False)
    estimated_kms = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    security_deposit = db.Column(db.Float, nullable=False)
    insurance_type = db.Column(db.String(50), nullable=False)
    license_number = db.Column(db.String(50), nullable=False)
    riding_experience = db.Column(db.Integer, nullable=False)
    has_verified_license = db.Column(db.Boolean, default=False)
    protection_plan = db.Column(db.String(50))
    training_requested = db.Column(db.Boolean, default=False)
    accessories = db.relationship('Accessory', secondary='ride_accessory', backref='rides')
    loyalty_points_earned = db.Column(db.Integer)
    applied_discount = db.Column(db.Float)
    bike = db.relationship('Bike', backref='rides')

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_value(key, default=None):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set_value(key, value, description=None):
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = Settings(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bike_id = db.Column(db.Integer, db.ForeignKey('bike.id'), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, cancelled, completed
    payment_status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='bookings')
    bike = db.relationship('Bike', backref='bookings')

# Sample bike data
sample_bikes = [
    {
        'name': 'Harley-Davidson LiveWire',
        'description': 'Revolutionary electric motorcycle combining Harley-Davidson\'s heritage with cutting-edge technology. Experience instant torque and a thrilling, silent ride.',
        'price': 15,  # Price per km
        'image': 'bikes/harley-livewire.jpg',
        'engine': 'Electric',
        'power': '105 HP',
        'mileage': '146 miles range',
        'type': 'Electric',
        'gallery_images': [
            'bikes/harley-livewire.jpg',
            'bikes/harley-livewire-2.jpg'
        ],
        'min_kms': 100  # Minimum kilometers for booking
    },
    {
        'name': 'BMW S1000RR',
        'description': 'The ultimate sport bike with cutting-edge technology and breathtaking performance. Features advanced electronics and race-bred engineering.',
        'price': 18,  # Price per km
        'image': 'bikes/bmw-s1000rr.jpg',
        'engine': '999 cc',
        'power': '205 HP',
        'mileage': '15 km/l',
        'type': 'Sport',
        'gallery_images': [
            'bikes/bmw-s1000rr.jpg',
            'bikes/bmw-s1000rr-2.jpg'
        ],
        'min_kms': 100
    },
    {
        'name': 'Yamaha R1',
        'description': 'Track-focused superbike with MotoGP-derived technology. Features electronic racing suspension and carbon fiber bodywork.',
        'price': 16,  # Price per km
        'image': 'bikes/yamaha-r1.jpg',
        'engine': '998 cc',
        'power': '200 HP',
        'mileage': '16 km/l',
        'type': 'Sport',
        'gallery_images': [
            'bikes/yamaha-r1.jpg',
            'bikes/yamaha-r1-2.jpg'
        ],
        'min_kms': 100
    },
    {
        'name': 'Indian Scout',
        'description': 'Modern American cruiser with stripped-down, blacked-out style. Perfect blend of classic design and modern performance.',
        'price': 12,  # Price per km
        'image': 'bikes/indian-scout.jpg',
        'engine': '1133 cc',
        'power': '100 HP',
        'mileage': '20 km/l',
        'type': 'Cruiser',
        'gallery_images': [
            'bikes/indian-scout.jpg',
            'bikes/indian-scout-2.jpg'
        ],
        'min_kms': 100
    },
    {
        'name': 'KTM Duke 890',
        'description': 'Aggressive street fighter with precise handling and thrilling performance. The perfect balance of power and agility.',
        'price': 10,  # Price per km
        'image': 'bikes/ktm-duke-890.jpg',
        'engine': '889 cc',
        'power': '115 HP',
        'mileage': '20 km/l',
        'type': 'Naked',
        'gallery_images': [
            'bikes/ktm-duke-890.jpg',
            'bikes/ktm-duke-890-forest.jpg'
        ],
        'min_kms': 50
    },
    {
        'name': 'Harley-Davidson Sportster',
        'description': 'Iconic American motorcycle combining classic styling with modern technology. Perfect for both city cruising and long rides.',
        'price': 11,  # Price per km
        'image': 'bikes/harley-sportster.jpg',
        'engine': '1200 cc',
        'power': '60 HP',
        'mileage': '18 km/l',
        'type': 'Cruiser',
        'gallery_images': [
            'bikes/harley-sportster.jpg',
            'bikes/harley-sportster-riding.jpg'
        ],
        'min_kms': 50
    },
    {
        'name': 'KTM RC 390',
        'description': 'Race-inspired design with powerful performance and agile handling. Perfect for both track days and daily commuting.',
        'price': 8,  # Price per km
        'image': 'bikes/ktm-rc390.jpg',
        'engine': '373.2 cc',
        'power': '43 HP',
        'mileage': '25 km/l',
        'type': 'Sport',
        'gallery_images': ['bikes/ktm-rc390.jpg'],
        'min_kms': 50
    }
]

# Sample data for loyalty tiers
loyalty_tiers = [
    {
        'name': 'Bronze',
        'min_points': 0,
        'discount_percentage': 0
    },
    {
        'name': 'Silver',
        'min_points': 1000,
        'discount_percentage': 5
    },
    {
        'name': 'Gold',
        'min_points': 5000,
        'discount_percentage': 10
    },
    {
        'name': 'Platinum',
        'min_points': 10000,
        'discount_percentage': 15
    }
]

# Sample data for accessories
sample_accessories = [
    {
        'name': 'Premium Helmet',
        'description': 'High-end motorcycle helmet with Bluetooth communication',
        'price_per_day': 500,
        'image': 'accessories/helmet.jpg'
    },
    {
        'name': 'Riding Jacket',
        'description': 'All-weather protective riding jacket with armor',
        'price_per_day': 400,
        'image': 'accessories/jacket.jpg'
    },
    {
        'name': 'GoPro Camera',
        'description': 'HD action camera with motorcycle mount',
        'price_per_day': 600,
        'image': 'accessories/gopro.jpg'
    },
    {
        'name': 'Tank Bag',
        'description': 'Magnetic tank bag for storage',
        'price_per_day': 200,
        'image': 'accessories/tankbag.jpg'
    },
    {
        'name': 'GPS Navigator',
        'description': 'Motorcycle-specific GPS device',
        'price_per_day': 300,
        'image': 'accessories/gps.jpg'
    }
]

# Routes
@app.route('/')
def index():
    # Get 3 featured bikes
    featured_bikes = Bike.query.filter_by(is_available=True).limit(3).all()
    return render_template('index.html', bikes=featured_bikes)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        is_driver = 'is_driver' in request.form

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            phone=phone,
            is_driver=is_driver,
            is_admin=False  # Only set to True manually for admin users
        )

        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out')
    return redirect(url_for('index'))

@app.route('/bikes')
def bikes():
    bikes = Bike.query.filter_by(is_available=True).all()
    return render_template('bikes.html', bikes=bikes)

@app.route('/bike/<int:bike_id>')
def bike_detail(bike_id):
    bike = Bike.query.get_or_404(bike_id)
    return render_template('bike_detail.html', bike=bike)

@app.route('/book-ride', methods=['POST'])
@login_required
def book_ride():
    try:
        data = request.get_json()
        
        # Validate dates
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d')
        if end_date <= start_date:
            return jsonify({'success': False, 'message': 'End date must be after start date'})
        
        # Check availability again (in case of race conditions)
        overlapping = Booking.query.filter(
            Booking.bike_id == data['bike_id'],
            Booking.status != 'cancelled',
            Booking.start_date <= end_date,
            Booking.end_date >= start_date
        ).first()
        
        if overlapping:
            return jsonify({'success': False, 'message': 'Bike is no longer available for the selected dates'})
        
        # Calculate price
        bike = Bike.query.get_or_404(data['bike_id'])
        duration = (end_date - start_date).days
        base_price = bike.price * duration
        
        # Calculate insurance cost
        insurance_cost = 500 if data['insurance'] == 'basic' else 1000
        insurance_cost *= duration
        
        # Calculate training cost
        training_cost = 2000 if data.get('training') else 0
        
        # Calculate total price
        total_price = base_price + insurance_cost + training_cost
        
        # Create booking
        booking = Booking(
            user_id=current_user.id,
            bike_id=data['bike_id'],
            start_date=start_date,
            end_date=end_date,
            total_price=total_price,
            status='pending'
        )
        
        db.session.add(booking)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Booking created successfully',
            'booking_id': booking.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/my-rides')
@login_required
def my_rides():
    rides = Ride.query.filter_by(user_id=current_user.id).all()
    return render_template('my_rides.html', rides=rides)

@app.route('/driver-rides')
@login_required
def driver_rides():
    if not current_user.is_driver:
        flash('Access denied')
        return redirect(url_for('index'))

    rides = Ride.query.filter_by(status='pending').all()
    return render_template('driver_rides.html', rides=rides)

@app.route('/accept-ride/<int:ride_id>')
@login_required
def accept_ride(ride_id):
    if not current_user.is_driver:
        flash('Access denied')
        return redirect(url_for('index'))

    ride = Ride.query.get(ride_id)
    if ride and ride.status == 'pending':
        ride.status = 'accepted'
        ride.driver_id = current_user.id
        db.session.commit()
        flash('Ride accepted successfully!')
    else:
        flash('Ride not available')

    return redirect(url_for('driver_rides'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    # Get statistics
    total_bikes = Bike.query.count()
    active_bookings = Ride.query.filter(Ride.status == 'upcoming').count()
    total_users = User.query.count()
    total_revenue = db.session.query(db.func.sum(Ride.total_price)).filter(Ride.status == 'completed').scalar() or 0
    
    # Get data for charts
    # Last 7 days bookings
    booking_dates = []
    booking_counts = []
    for i in range(6, -1, -1):
        date = datetime.now() - timedelta(days=i)
        count = Ride.query.filter(
            db.func.date(Ride.pickup_date) == date.date()
        ).count()
        booking_dates.append(date.strftime('%d %b'))
        booking_counts.append(count)
    
    # Bike utilization
    total_bikes = Bike.query.count()
    booked_bikes = Ride.query.filter(
        Ride.status == 'upcoming',
        Ride.pickup_date <= datetime.now(),
        Ride.dropoff_date >= datetime.now()
    ).count()
    maintenance_bikes = Bike.query.filter_by(is_available=False).count()
    available_bikes = total_bikes - booked_bikes - maintenance_bikes
    bike_utilization = [available_bikes, booked_bikes, maintenance_bikes]
    
    # Revenue data (last 6 months)
    revenue_months = []
    revenue_data = []
    for i in range(5, -1, -1):
        month = datetime.now() - timedelta(days=30*i)
        revenue = db.session.query(db.func.sum(Ride.total_price)).filter(
            Ride.status == 'completed',
            db.func.month(Ride.pickup_date) == month.month,
            db.func.year(Ride.pickup_date) == month.year
        ).scalar() or 0
        revenue_months.append(month.strftime('%b %Y'))
        revenue_data.append(revenue)
    
    # User growth (last 6 months)
    user_months = []
    user_data = []
    for i in range(5, -1, -1):
        month = datetime.now() - timedelta(days=30*i)
        new_users = User.query.filter(
            db.func.month(User.created_at) == month.month,
            db.func.year(User.created_at) == month.year
        ).count()
        user_months.append(month.strftime('%b %Y'))
        user_data.append(new_users)
    
    # Get all bikes, bookings, and users
    bikes = Bike.query.all()
    bookings = Ride.query.order_by(Ride.pickup_date.desc()).all()
    users = User.query.all()
    
    # Get system settings
    settings = {
        'min_distance': Settings.get_value('min_distance', '100'),
        'security_deposit': Settings.get_value('security_deposit', '5000'),
        'points_per_100': Settings.get_value('points_per_100', '10'),
        'cancellation_fee': Settings.get_value('cancellation_fee', '20')
    }
    
    return render_template('admin/dashboard.html',
                         total_bikes=total_bikes,
                         active_bookings=active_bookings,
                         total_users=total_users,
                         total_revenue=total_revenue,
                         booking_dates=booking_dates,
                         booking_counts=booking_counts,
                         bike_utilization=bike_utilization,
                         revenue_months=revenue_months,
                         revenue_data=revenue_data,
                         user_months=user_months,
                         user_data=user_data,
                         bikes=bikes,
                         bookings=bookings,
                         users=users,
                         settings=settings)

@app.route('/admin/add-bike', methods=['POST'])
@login_required
def add_bike():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        name = request.form.get('name')
        type = request.form.get('type')
        price = float(request.form.get('price'))
        min_kms = int(request.form.get('min_kms'))
        image = request.files.get('image')
        
        if not all([name, type, price, min_kms, image]):
            return jsonify({'success': False, 'message': 'All fields are required'})
        
        # Save image
        filename = secure_filename(image.filename)
        image_path = os.path.join('static', 'images', 'bikes', filename)
        image.save(os.path.join(app.root_path, image_path))
        
        # Create new bike
        bike = Bike(
            name=name,
            type=type,
            price=price,
            min_kms=min_kms,
            image=image_path,
            is_available=True
        )
        db.session.add(bike)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/delete-bike/<int:id>', methods=['POST'])
@login_required
def delete_bike(id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        bike = Bike.query.get_or_404(id)
        
        # Delete image file
        if bike.image:
            try:
                os.remove(os.path.join(app.root_path, bike.image))
            except:
                pass
        
        db.session.delete(bike)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/cancel-booking/<int:id>', methods=['POST'])
@login_required
def admin_cancel_booking(id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        ride = Ride.query.get_or_404(id)
        
        # Get cancellation fee from settings
        cancellation_fee = float(Settings.get_value('cancellation_fee', '20'))
        refund_amount = ride.total_price * (1 - cancellation_fee/100)
        
        # Update ride status
        ride.status = 'cancelled'
        ride.refund_amount = refund_amount
        
        # Make bike available
        ride.bike.is_available = True
        
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/delete-user/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        user = User.query.get_or_404(id)
        
        # Delete user's rides
        Ride.query.filter_by(user_id=id).delete()
        
        # Delete user's loyalty data
        if user.loyalty:
            db.session.delete(user.loyalty)
        
        # Delete user
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/update-settings', methods=['POST'])
@login_required
def update_settings():
    if not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    try:
        Settings.set_value('min_distance', request.form.get('min_distance'), 
                         'Minimum booking distance in kilometers')
        Settings.set_value('security_deposit', request.form.get('security_deposit'),
                         'Security deposit amount in rupees')
        Settings.set_value('points_per_100', request.form.get('points_per_100'),
                         'Loyalty points earned per 100 rupees spent')
        Settings.set_value('cancellation_fee', request.form.get('cancellation_fee'),
                         'Cancellation fee percentage')
        
        flash('Settings updated successfully', 'success')
    except Exception as e:
        flash(f'Error updating settings: {str(e)}', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export-<type>')
@login_required
def export_report(type):
    if not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    try:
        if type == 'bookings':
            rides = Ride.query.all()
            data = [{
                'ID': ride.id,
                'User': ride.user.name,
                'Bike': ride.bike.name,
                'Pickup Date': ride.pickup_date.strftime('%d %b %Y'),
                'Distance': f"{ride.estimated_kms} km",
                'Total Price': f"₹{ride.total_price}",
                'Status': ride.status.title()
            } for ride in rides]
            filename = 'bookings.csv'
        
        elif type == 'users':
            users = User.query.all()
            data = [{
                'Name': user.name,
                'Email': user.email,
                'Phone': user.phone,
                'License': user.license_number,
                'Loyalty Tier': user.loyalty.tier.name if user.loyalty else 'Not Enrolled',
                'Status': 'Active' if user.is_active else 'Inactive'
            } for user in users]
            filename = 'users.csv'
        
        elif type == 'revenue':
            rides = Ride.query.filter_by(status='completed').all()
            data = [{
                'ID': ride.id,
                'Date': ride.pickup_date.strftime('%d %b %Y'),
                'User': ride.user.name,
                'Bike': ride.bike.name,
                'Distance': f"{ride.estimated_kms} km",
                'Amount': f"₹{ride.total_price}"
            } for ride in rides]
            filename = 'revenue.csv'
        
        else:
            flash('Invalid report type', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Create CSV file
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        
        # Return CSV file
        output.seek(0)
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    
    except Exception as e:
        flash(f'Error generating report: {str(e)}', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/health')
def health_check():
    try:
        # Test database connection
        with db.engine.connect() as conn:
            conn.execute("SELECT 1")
            return jsonify({
                'status': 'healthy',
                'database': 'connected',
                'timestamp': datetime.utcnow().isoformat()
            }), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Server Error: {error}")
    return render_template('500.html'), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

def init_db():
    with app.app_context():
        try:
            db.create_all()
            
            # Add loyalty tiers if they don't exist
            if LoyaltyTier.query.count() == 0:
                for tier_data in loyalty_tiers:
                    tier = LoyaltyTier(**tier_data)
                    db.session.add(tier)

            # Add accessories if they don't exist
            if Accessory.query.count() == 0:
                for acc_data in sample_accessories:
                    accessory = Accessory(**acc_data)
                    db.session.add(accessory)

            # Add sample bikes if they don't exist
            if Bike.query.count() == 0:
                for bike_data in sample_bikes:
                    bike = Bike(**bike_data)
                    db.session.add(bike)

            # Initialize default settings if they don't exist
            default_settings = {
                'min_distance': ('100', 'Minimum booking distance in kilometers'),
                'security_deposit': ('5000', 'Security deposit amount in rupees'),
                'points_per_100': ('10', 'Loyalty points earned per 100 rupees spent'),
                'cancellation_fee': ('20', 'Cancellation fee percentage')
            }
            
            for key, (value, description) in default_settings.items():
                if not Settings.query.filter_by(key=key).first():
                    setting = Settings(key=key, value=value, description=description)
                    db.session.add(setting)

            db.session.commit()
            print("Database initialized successfully")
        except Exception as e:
            print(f"Error initializing database: {str(e)}")

# Test database connection with retry
def test_db_connection(max_retries=3):
    for attempt in range(max_retries):
        try:
            with db.engine.connect() as conn:
                conn.execute("SELECT 1")
                logger.info("Database connection successful")
                return True
        except Exception as e:
            logger.error(f"Database connection attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                return False
            time.sleep(2)  # Wait before retrying
    return False

@app.before_first_request
def initialize_database():
    try:
        if test_db_connection():
            db.create_all()
            init_db()
            logger.info("Database initialized successfully")
        else:
            logger.error("Failed to initialize database")
    except Exception as e:
        logger.error(f"Error during database initialization: {str(e)}")

@app.route('/check-availability', methods=['POST'])
def check_availability():
    data = request.get_json()
    bike_id = data.get('bike_id')
    start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d')
    
    # Check for overlapping bookings
    overlapping = Booking.query.filter(
        Booking.bike_id == bike_id,
        Booking.status != 'cancelled',
        Booking.start_date <= end_date,
        Booking.end_date >= start_date
    ).first()
    
    return jsonify({
        'available': not bool(overlapping)
    })

@app.route('/calculate-price', methods=['POST'])
def calculate_price():
    data = request.get_json()
    bike_id = data.get('bike_id')
    start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d')
    
    bike = Bike.query.get_or_404(bike_id)
    duration = (end_date - start_date).days
    
    # Base price calculation
    base_price = bike.price * duration
    
    # Apply any discounts or additional charges
    total_price = base_price
    
    return jsonify({
        'base_price': base_price,
        'total_price': total_price,
        'duration': duration
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False) 