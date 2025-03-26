from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
import requests
from models import Prayer  # Prayer modelini import qilish
from models import db, User, Prayer
from datetime import datetime
from telebot import TeleBot, types
import os


  # Shu yerga web sahifang URLini qo‘y




# SQLAlchemy obyektini yaratish
db = SQLAlchemy()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'supersecretkey'

# Kutubxonalarni ilovaga bog‘lash
db.init_app(app)
bcrypt = Bcrypt(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# O‘zbekiston shaharlari
CITIES = ["Toshkent", "Samarqand", "Buxoro", "Xiva", "Namangan", "Andijon", "Farg‘ona", "Qo‘qon", "Navoiy", "Qarshi", "Jizzax"]


# Namozlarni saqlash modeli
class Prayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    fajr = db.Column(db.Boolean, default=False)
    dhuhr = db.Column(db.Boolean, default=False)
    asr = db.Column(db.Boolean, default=False)
    maghrib = db.Column(db.Boolean, default=False)
    isha = db.Column(db.Boolean, default=False)


# Namoz tahlili sahifasi
@app.route('/prayer-analysis', methods=['GET', 'POST'])
@login_required
def prayer_analysis():
    prayers = []
    
    start_date = None
    end_date = None
    
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        if start_date and end_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            prayers = Prayer.query.filter(
                Prayer.user_id == current_user.id,
                Prayer.date >= start_date,
                Prayer.date <= end_date
            ).all()
    
    return render_template('prayer_analysis.html', prayers=prayers, start_date=start_date, end_date=end_date)


@app.route('/mark-prayer', methods=['GET', 'POST'])
@login_required
def mark_prayer():
    region = current_user.region
    prayer_times = get_prayer_times(region)  # API orqali namoz vaqtlarini olish

    if not prayer_times:
        flash("Namoz vaqtlari yuklanmadi, iltimos qayta urinib ko‘ring!", "danger")
        return redirect(url_for("dashboard"))

    current_time = datetime.now().strftime("%H:%M")
    available_prayers = {prayer: time for prayer, time in prayer_times.items() if time <= current_time}

    if request.method == 'POST':
        selected_prayers = request.form.getlist('prayer')  # Belgilangan namozlar

        today = datetime.today().date()
        existing_record = Prayer.query.filter_by(user_id=current_user.id, date=today).first()

        if existing_record:
            for prayer in selected_prayers:
                setattr(existing_record, prayer.lower(), True)
        else:
            new_prayer = Prayer(
                user_id=current_user.id,
                date=today,
                fajr='Bomdod' in selected_prayers,
                dhuhr='Peshin' in selected_prayers,
                asr='Asr' in selected_prayers,
                maghrib='Shom' in selected_prayers,
                isha='Xufton' in selected_prayers
            )
            db.session.add(new_prayer)

        db.session.commit()
        flash("Namoz belgilandi!", "success")
        return redirect(url_for('dashboard'))  # Dashboard sahifasiga qaytish

    return render_template('mark_prayer.html', prayer_times=available_prayers, current_time=current_time)

    
# Foydalanuvchi modeli
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    region = db.Column(db.String(100), nullable=True)
    prayers = db.relationship('Prayer', backref='user', lazy=True)

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

# Namoz vaqtlari API dan olish funksiyasi
def get_prayer_times(region):
    url = f"https://api.aladhan.com/v1/timingsByCity?city={region}&country=Uzbekistan&method=2"
    response = requests.get(url)
    data = response.json()

    if response.status_code == 200:
        timings = data["data"]["timings"]
        prayer_times = {
            "Bomdod": timings["Fajr"],
            "Peshin": timings["Dhuhr"],
            "Asr": timings["Asr"],
            "Shom": timings["Maghrib"],
            "Xufton": timings["Isha"]
        }
        return prayer_times
    else:
        return None


from flask import request, jsonify

@app.route('/dashboard')
@login_required
def dashboard():
    region = current_user.region  # Foydalanuvchining tanlagan hududi
    prayer_times = get_prayer_times(region)  # API orqali namoz vaqtlarini olish
    
    today = datetime.today().date()  # Bugungi sana
    today_prayer = Prayer.query.filter_by(user_id=current_user.id, date=today).first()  # Bugungi namozlar
    
    # Agar so'rov JSON formatda bo'lsa, JSON ma'lumot qaytarish
    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            "region": region,
            "prayer_times": prayer_times,
            "today_prayer": {
                "fajr": today_prayer.fajr if today_prayer else False,
                "dhuhr": today_prayer.dhuhr if today_prayer else False,
                "asr": today_prayer.asr if today_prayer else False,
                "maghrib": today_prayer.maghrib if today_prayer else False,
                "isha": today_prayer.isha if today_prayer else False
            }
        })
    
    return render_template('dashboard.html', prayer_times=prayer_times, region=region, today_prayer=today_prayer)


@app.route('/save-prayer', methods=['POST'])
@login_required
def save_prayer():
    today = datetime.today().date()

    # Formdan kelayotgan belgilangan namozlar
    prayers = request.form.getlist('prayer')  # HTML shaklidagi checkbox nomi 'prayer' bo‘lishi kerak
    fajr = 'Bomdod' in prayers
    dhuhr = 'Peshin' in prayers
    asr = 'Asr' in prayers
    maghrib = 'Shom' in prayers
    isha = 'Xufton' in prayers

    # Bugungi kun uchun namoz yozilgan-yozilmaganligini tekshiramiz
    existing_prayer = Prayer.query.filter_by(user_id=current_user.id, date=today).first()

    if existing_prayer:
        existing_prayer.fajr = fajr
        existing_prayer.dhuhr = dhuhr
        existing_prayer.asr = asr
        existing_prayer.maghrib = maghrib
        existing_prayer.isha = isha
    else:
        new_prayer = Prayer(
            user_id=current_user.id,
            date=today,
            fajr=fajr,
            dhuhr=dhuhr,
            asr=asr,
            maghrib=maghrib,
            isha=isha
        )
        db.session.add(new_prayer)

    db.session.commit()
    flash('Namozlar muvaffaqiyatli saqlandi!', 'success')

    return redirect(url_for('dashboard'))



# Bazani yaratish yoki mavjudligini tekshirish
with app.app_context():
    db.create_all()
    print("✅ Baza yaratildi yoki allaqachon mavjud!")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Ro‘yxatdan o‘tish
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        region = request.form.get('region', 'tashkent')  # Default hudud

        # Takroriy username va emailni tekshirish
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Bu foydalanuvchi nomi allaqachon mavjud!', 'danger')
            return redirect(url_for('register'))

        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Bu email allaqachon ishlatilgan!', 'danger')
            return redirect(url_for('register'))

        new_user = User(username=username, email=email, region=region)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Ro‘yxatdan muvaffaqiyatli o‘tdingiz! Endi tizimga kiring.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login qilish
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Tizimga muvaffaqiyatli kirdingiz!', 'success')
            return redirect(url_for('dashboard'))  # Login muvaffaqiyatli bo'lsa dashboardga o'tkaziladi
        else:
            flash('Login yoki parol noto‘g‘ri!', 'danger')  # Faqat login sahifasida chiqadi

    return render_template('login.html')

# Logout qilish
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Tizimdan chiqdingiz!', 'info')
    return redirect(url_for('login'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        new_region = request.form.get('region')
        new_language = request.form.get('language')

        # Foydalanuvchi ma’lumotlarini yangilash
        current_user.region = new_region
        current_user.language = new_language
        db.session.commit()

        flash("Muvaffaqiyatli saqlandi!", "success")
        return redirect(url_for('settings'))

    return render_template('settings.html')




# Asosiy sahifa
@app.route('/')
def home():
    return redirect(url_for('login'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Baza yaratish
    app.run(debug=True)
