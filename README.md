# RideWave - Ride Sharing Platform

RideWave is a modern ride-sharing platform that connects drivers and passengers seamlessly. This project includes a complete web application with frontend, backend, and database integration.

## Features

- User registration and authentication
- Ride booking system
- Driver and passenger roles
- Ride management
- Modern and responsive UI
- SQLite database integration

## Tech Stack

- Frontend: HTML, CSS
- Backend: Python (Flask)
- Database: SQLite
- Additional: Font Awesome for icons

## Setup Instructions

1. Clone the repository:
```bash
git clone <repository-url>
cd ridewave
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Initialize the database:
```bash
python
>>> from app import app, db
>>> app.app_context().push()
>>> db.create_all()
>>> exit()
```

5. Run the application:
```bash
python app.py
```

6. Open your browser and navigate to:
```
http://localhost:5000
```

## Project Structure

```
ridewave/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── static/
│   ├── css/
│   │   └── style.css  # Main stylesheet
│   └── images/        # Image assets
├── templates/         # HTML templates
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── book_ride.html
│   └── my_rides.html
└── ridewave.db       # SQLite database (created after first run)
```

## Usage

1. Register as a new user (either as a passenger or driver)
2. Login to your account
3. Book a ride (as a passenger) or accept rides (as a driver)
4. Manage your rides through the "My Rides" section

## Contributing

Feel free to submit issues and enhancement requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 