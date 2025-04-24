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
from logging.handlers import RotatingFileHandler
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add file handler for logging
if not os.path.exists('logs'):
    os.makedirs('logs')
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)

app = Flask(__name__)

# Configure database URL for Railway
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

# Configure secret key
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))

# Configure SQLAlchemy
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
    type = db.Column(db.String(50))  # Sport, Cruiser, Touring, etc.
    gallery_images = db.Column(db.JSON)
    is_available = db.Column(db.Boolean, default=True)
    min_kms = db.Column(db.Integer, nullable=False)
    is_premium = db.Column(db.Boolean, default=False)
    features = db.Column(db.JSON)  # Premium features like ABS, Traction Control, etc.
    specifications = db.Column(db.JSON)  # Detailed specs
    safety_rating = db.Column(db.Float)  # Safety rating out of 5
    comfort_rating = db.Column(db.Float)  # Comfort rating out of 5
    performance_rating = db.Column(db.Float)  # Performance rating out of 5
    maintenance_history = db.Column(db.JSON)  # Service history
    last_service_date = db.Column(db.DateTime)
    next_service_date = db.Column(db.DateTime)
    service_interval = db.Column(db.Integer)  # Service interval in kilometers

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
        'name': 'Ducati Panigale V4',
        'description': 'The ultimate Italian superbike with cutting-edge technology and breathtaking performance. Features advanced electronics and race-bred engineering.',
        'price': 15000,  # Price per day
        'image': 'bikes/ducati-panigale.jpg',
        'engine': '1103 cc',
        'power': '214 HP',
        'mileage': '12 km/l',
        'type': 'Sport',
        'gallery_images': [
            'bikes/ducati-panigale-1.jpg',
            'bikes/ducati-panigale-2.jpg'
        ],
        'min_kms': 100,
        'is_premium': True,
        'features': {
            'ABS': 'Yes',
            'Traction Control': 'Yes',
            'Riding Modes': 'Race, Sport, Street, Wet',
            'Electronic Suspension': 'Yes',
            'Quick Shifter': 'Yes',
            'Launch Control': 'Yes'
        },
        'specifications': {
            'Top Speed': '299 km/h',
            '0-100 km/h': '2.9 seconds',
            'Weight': '198 kg',
            'Fuel Capacity': '16L',
            'Seat Height': '830 mm'
        },
        'safety_rating': 4.8,
        'comfort_rating': 3.9,
        'performance_rating': 5.0,
        'maintenance_history': [
            {'date': '2024-01-15', 'service': 'Full Service', 'kms': 5000},
            {'date': '2024-03-20', 'service': 'Oil Change', 'kms': 7500}
        ],
        'last_service_date': datetime(2024, 3, 20),
        'next_service_date': datetime(2024, 6, 20),
        'service_interval': 5000
    },
    {
        'name': 'BMW S1000RR',
        'description': 'German engineering excellence with perfect balance of power and precision. Features advanced aerodynamics and race-ready performance.',
        'price': 12000,
        'image': 'bikes/bmw-s1000rr.jpg',
        'engine': '999 cc',
        'power': '205 HP',
        'mileage': '15 km/l',
        'type': 'Sport',
        'gallery_images': [
            'bikes/bmw-s1000rr-1.jpg',
            'bikes/bmw-s1000rr-2.jpg'
        ],
        'min_kms': 100,
        'is_premium': True,
        'features': {
            'ABS': 'Yes',
            'Traction Control': 'Yes',
            'Riding Modes': 'Race, Sport, Rain, User',
            'Electronic Suspension': 'Yes',
            'Quick Shifter': 'Yes',
            'Launch Control': 'Yes'
        },
        'specifications': {
            'Top Speed': '303 km/h',
            '0-100 km/h': '3.1 seconds',
            'Weight': '197 kg',
            'Fuel Capacity': '16.5L',
            'Seat Height': '824 mm'
        },
        'safety_rating': 4.7,
        'comfort_rating': 4.0,
        'performance_rating': 4.9,
        'maintenance_history': [
            {'date': '2024-02-10', 'service': 'Full Service', 'kms': 6000},
            {'date': '2024-04-15', 'service': 'Oil Change', 'kms': 8500}
        ],
        'last_service_date': datetime(2024, 4, 15),
        'next_service_date': datetime(2024, 7, 15),
        'service_interval': 5000
    },
    {
        'name': 'Harley-Davidson CVO Limited',
        'description': 'The pinnacle of American luxury touring. Features premium comfort and state-of-the-art technology for the ultimate riding experience.',
        'price': 10000,
        'image': 'bikes/harley-cvo.jpg',
        'engine': '1923 cc',
        'power': '97 HP',
        'mileage': '18 km/l',
        'type': 'Touring',
        'gallery_images': [
            'bikes/harley-cvo-1.jpg',
            'bikes/harley-cvo-2.jpg'
        ],
        'min_kms': 50,
        'is_premium': True,
        'features': {
            'ABS': 'Yes',
            'Traction Control': 'Yes',
            'Riding Modes': 'Tour, Sport, Rain',
            'Cruise Control': 'Yes',
            'Infotainment System': 'Yes',
            'Heated Seats': 'Yes'
        },
        'specifications': {
            'Top Speed': '180 km/h',
            '0-100 km/h': '4.5 seconds',
            'Weight': '417 kg',
            'Fuel Capacity': '22.7L',
            'Seat Height': '740 mm'
        },
        'safety_rating': 4.6,
        'comfort_rating': 4.9,
        'performance_rating': 4.5,
        'maintenance_history': [
            {'date': '2024-01-20', 'service': 'Full Service', 'kms': 8000},
            {'date': '2024-03-25', 'service': 'Oil Change', 'kms': 10000}
        ],
        'last_service_date': datetime(2024, 3, 25),
        'next_service_date': datetime(2024, 6, 25),
        'service_interval': 5000
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
        db.engine.connect()
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

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error
    logger.error(f"Unhandled Exception: {str(e)}")
    logger.error(traceback.format_exc())
    
    # Return a proper error response
    return jsonify({
        'error': 'Internal Server Error',
        'message': str(e),
        'traceback': traceback.format_exc() if app.debug else None
    }), 500

@app.before_request
def before_request():
    logger.info(f"Request: {request.method} {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Data: {request.get_data()}")

@app.after_request
def after_request(response):
    logger.info(f"Response: {response.status}")
    return response

def init_db():
    try:
        with app.app_context():
            # Test database connection
            db.engine.connect()
            logger.info("Database connection successful")
            
            # Create tables
            db.create_all()
            logger.info("Database tables created")
            
            # Initialize sample data
            if Bike.query.count() == 0:
                for bike_data in sample_bikes:
                    bike = Bike(**bike_data)
                    db.session.add(bike)
                db.session.commit()
                logger.info("Sample bikes added to database")
            
            if Settings.query.count() == 0:
                settings = Settings(
                    security_deposit=5000,
                    points_per_100=10,
                    cancellation_fee=20
                )
                db.session.add(settings)
                db.session.commit()
                logger.info("Default settings added to database")
            
            logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        logger.error(traceback.format_exc())
        raise

if __name__ == '__main__':
    try:
        # Initialize database
        init_db()
        
        # Start the application
        logger.info("Starting application...")
        app.run(host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1) 