from flask import Flask, abort, flash, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, timedelta, timezone
from decimal import Decimal, InvalidOperation
import os
import uuid
from models import (
    Booking,
    ChatMessage,
    Machinery,
    MachineryRental,
    Notification,
    Payment,
    Review,
    Tractor,
    TractorRental,
    User,
    Worker,
    db,
)

load_dotenv()

app = Flask(__name__)


@app.template_filter("local_datetime")
def format_local_datetime(value):
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%b %d, %Y at %I:%M %p")

app.secret_key = "agroease-secret-key-change-this-later"

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)


def save_uploaded_image(upload):
    if upload is None or not upload.filename:
        return None

    extension = os.path.splitext(upload.filename)[1].lower().lstrip(".")
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Choose a JPG, JPEG, PNG, or WEBP image.")

    filename = f"{uuid.uuid4().hex}.{extension}"
    upload.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename


def notify_user(user_id, message, notification_type):
    db.session.add(Notification(
        user_id=user_id,
        message=message,
        notification_type=notification_type,
    ))


def parse_rental_dates(form):
    start_text = form.get("start_date") or form.get("rental_date", "")
    end_text = form.get("end_date") or start_text
    try:
        start_date = date.fromisoformat(start_text)
        end_date = date.fromisoformat(end_text)
    except ValueError as error:
        raise ValueError("Enter valid rental start and end dates.") from error

    if start_date < date.today():
        raise ValueError("Rental dates cannot be in the past.")
    if end_date < start_date:
        raise ValueError("The end date must be on or after the start date.")
    return start_date, end_date


def rental_dates_conflict(rental_model, equipment_column, equipment_id, start_date, end_date):
    requested_range_overlap = db.and_(
        rental_model.start_date.isnot(None),
        rental_model.start_date <= end_date,
        rental_model.end_date >= start_date,
    )
    legacy_single_date_overlap = db.and_(
        rental_model.start_date.is_(None),
        rental_model.rental_date >= start_date,
        rental_model.rental_date <= end_date,
    )
    return rental_model.query.filter(
        equipment_column == equipment_id,
        rental_model.status.in_(("Pending", "Accepted")),
        db.or_(requested_range_overlap, legacy_single_date_overlap),
    ).first() is not None


def get_equipment_availability(rental_model, equipment_column, equipment_id, listing_available):
    rentals = rental_model.query.filter(equipment_column == equipment_id).all()
    has_booking_history = any(
        rental.status in ("Pending", "Accepted", "Completed")
        for rental in rentals
    )
    today = date.today()
    active_ranges = []
    for rental in rentals:
        if rental.status not in ("Pending", "Accepted"):
            continue
        start_date = rental.start_date or rental.rental_date
        end_date = rental.end_date or start_date
        if end_date >= today:
            active_ranges.append((start_date, end_date))

    booked_until = max((end_date for _, end_date in active_ranges), default=None)
    return {
        "is_listed": listing_available or has_booking_history,
        "is_booked": bool(active_ranges),
        "booked_until": booked_until,
        "available_from": booked_until + timedelta(days=1) if booked_until else today,
    }


def can_chat_between(first_user, second_user):
    valid_roles = {"Worker", "Equipment Owner"}
    return (
        first_user.id != second_user.id
        and (
            ("Farmer" in first_user.account_roles and bool(valid_roles.intersection(second_user.account_roles)))
            or ("Farmer" in second_user.account_roles and bool(valid_roles.intersection(first_user.account_roles)))
        )
    )


def get_review_summary(reviews):
    if not reviews:
        return None, 0
    return round(sum(review.rating for review in reviews) / len(reviews), 1), len(reviews)
@app.route("/")
def home():
    return render_template("index.html")
@app.route("/test-db")
def test_db():
    try:
        db.session.execute(db.text("SELECT 1"))
        return "Database connected successfully!"
    except Exception as e:
        return f"Database connection failed: {e}"
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        roles = request.form.getlist("roles")
        valid_roles = {"Farmer", "Worker", "Equipment Owner"}

        if not name or not email:
            flash("Enter your name and email address.", "error")
            return render_template("register.html"), 400
        if not roles or len(roles) != len(set(roles)) or not set(roles).issubset(valid_roles):
            flash("Choose at least one valid account role.", "error")
            return render_template("register.html"), 400
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html"), 400
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("Email already registered. Please use another email.", "error")
            return render_template("register.html"), 409
        hashed_password = generate_password_hash(password)

        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            role=roles[0],
            roles=",".join(roles),
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("register.html")
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        selected_role = request.form.get("role", "").strip()
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            available_roles = user.account_roles
            if not selected_role:
                selected_role = user.role
            if selected_role not in available_roles:
                flash("Choose a role linked to your account.", "error")
                return render_template("login.html"), 403
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_role"] = selected_role

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")
        return render_template("login.html"), 401

    return render_template("login.html")


@app.route("/switch-role", methods=["POST"])
def switch_role():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.session.get(User, session["user_id"])
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    selected_role = request.form.get("role", "").strip()
    if selected_role not in user.account_roles:
        abort(403)

    session["user_role"] = selected_role
    flash(f"Switched to your {selected_role} account.", "success")
    return redirect(url_for("profile"))
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.session.get(User, session["user_id"])
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    unread_count = Notification.query.filter_by(
        user_id=session["user_id"],
        is_read=False,
    ).count()

    owner_tractors = []
    owner_machinery = []
    worker = None
    if session.get("user_role") == "Equipment Owner":
        owner_tractors = Tractor.query.filter_by(
            owner_id=session["user_id"],
        ).order_by(Tractor.id.desc()).all()
        owner_machinery = Machinery.query.filter_by(
            owner_id=session["user_id"],
        ).order_by(Machinery.id.desc()).all()
    elif session.get("user_role") == "Worker":
        worker = Worker.query.filter_by(user_id=session["user_id"]).first()

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        role=session["user_role"],
        worker=worker,
        unread_count=unread_count,
        owner_tractors=owner_tractors,
        owner_machinery=owner_machinery,
    )


@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_notifications = Notification.query.filter_by(
        user_id=session["user_id"]
    ).order_by(Notification.created_at.desc()).all()
    return render_template("notifications.html", notifications=user_notifications)


@app.route("/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=session["user_id"],
    ).first_or_404()
    notification.is_read = True
    db.session.commit()
    return redirect(url_for("notifications"))


@app.route("/chats")
def chats():
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = db.session.get(User, session["user_id"])
    if current_user is None:
        session.clear()
        return redirect(url_for("login"))

    messages = ChatMessage.query.filter(
        db.or_(
            ChatMessage.sender_id == current_user.id,
            ChatMessage.receiver_id == current_user.id,
        )
    ).order_by(ChatMessage.created_at.desc()).all()

    latest_by_partner = {}
    for message in messages:
        partner_id = message.receiver_id if message.sender_id == current_user.id else message.sender_id
        if partner_id in latest_by_partner:
            continue
        partner = db.session.get(User, partner_id)
        if partner and can_chat_between(current_user, partner):
            latest_by_partner[partner_id] = (partner, message)

    return render_template(
        "chats.html",
        conversations=list(latest_by_partner.values()),
    )


@app.route("/chat/<int:other_user_id>", methods=["GET", "POST"])
def chat(other_user_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = User.query.get_or_404(session["user_id"])
    other_user = User.query.get_or_404(other_user_id)
    if not can_chat_between(current_user, other_user):
        return "Chat is available only between farmers and workers or equipment owners.", 403

    if request.method == "POST":
        message_text = request.form.get("message", "").strip()
        if not message_text or len(message_text) > 2000:
            flash("Messages must contain between 1 and 2000 characters.", "error")
        else:
            db.session.add(ChatMessage(
                sender_id=current_user.id,
                receiver_id=other_user.id,
                message=message_text,
            ))
            notify_user(
                other_user.id,
                f"New message from {current_user.name}.",
                "new_message",
            )
            db.session.commit()
            return redirect(url_for("chat", other_user_id=other_user.id))

    messages = ChatMessage.query.filter(
        db.or_(
            db.and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == other_user.id),
            db.and_(ChatMessage.sender_id == other_user.id, ChatMessage.receiver_id == current_user.id),
        )
    ).order_by(ChatMessage.created_at.asc()).all()
    return render_template(
        "chat.html",
        current_user=current_user,
        other_user=other_user,
        messages=messages,
    )
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get_or_404(session["user_id"])
    return render_template(
        "profile.html",
        user=user,
        role=session.get("user_role", user.role),
        account_roles=user.account_roles,
    )


@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get_or_404(session["user_id"])
    worker = user.worker_profile
    previous_name = user.name
    role = session.get("user_role", user.role)
    payment_roles = {"Worker", "Equipment Owner"}
    online_payment_labels = {
        "net_banking": "Net Banking",
        "debit_card": "Debit Card",
        "qr_code": "QR Code",
    }

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        selected_payment_methods = []

        if not 2 <= len(name) <= 100:
            flash("Name must contain between 2 and 100 characters.", "error")
            return render_template("edit_profile.html", user=user, worker=worker, role=role)
        if not 7 <= len(phone) <= 20 or not all(
            character.isdigit() or character in "+() -" for character in phone
        ):
            flash("Enter a valid phone number.", "error")
            return render_template("edit_profile.html", user=user, worker=worker, role=role)
        if not location or len(location) > 100:
            flash("Location is required and must be under 100 characters.", "error")
            return render_template("edit_profile.html", user=user, worker=worker, role=role)

        if role in payment_roles:
            selected_payment_methods = list(dict.fromkeys(
                method for method in request.form.getlist("online_payment_methods")
                if method in online_payment_labels
            ))
            bank_name = request.form.get("bank_name", "").strip()
            bank_account_number = request.form.get("bank_account_number", "").strip()
            cardholder_name = request.form.get("demo_cardholder_name", "").strip()
            demo_card_number = request.form.get("demo_card_number", "").strip()
            demo_card_expiry = request.form.get("demo_card_expiry", "").strip()
            try:
                valid_demo_card_expiry = (
                    len(demo_card_expiry) == 7
                    and date.fromisoformat(f"{demo_card_expiry}-01") >= date.today().replace(day=1)
                )
            except ValueError:
                valid_demo_card_expiry = False
            remove_qr_code = request.form.get("remove_qr_code") == "true"
            qr_upload = request.files.get("qr_code")
            qr_filename = None

            if "net_banking" in selected_payment_methods and (
                not bank_name or len(bank_name) > 100
                or not bank_account_number.isdigit()
                or not 6 <= len(bank_account_number) <= 34
            ):
                flash("Add a bank name and a valid 6 to 34 digit account number for Net Banking.", "error")
                return render_template("edit_profile.html", user=user, worker=worker, role=role)

            if "debit_card" in selected_payment_methods and (
                not 2 <= len(cardholder_name) <= 100
                or len(demo_card_number) != 6
                or not demo_card_number.isdigit()
                or not valid_demo_card_expiry
            ):
                flash("Demo Debit Card requires a cardholder name, a six-digit demo number, and a valid current or future expiry month.", "error")
                return render_template("edit_profile.html", user=user, worker=worker, role=role)

            if "qr_code" in selected_payment_methods:
                if remove_qr_code and (qr_upload is None or not qr_upload.filename):
                    flash("Upload a QR code before removing the current one.", "error")
                    return render_template("edit_profile.html", user=user, worker=worker, role=role)
                if qr_upload is None or not qr_upload.filename:
                    if not user.qr_code_filename or remove_qr_code:
                        flash("Upload a QR code image to enable QR Code payments.", "error")
                        return render_template("edit_profile.html", user=user, worker=worker, role=role)
                else:
                    try:
                        qr_filename = save_uploaded_image(qr_upload)
                    except ValueError as error:
                        flash(str(error), "error")
                        return render_template("edit_profile.html", user=user, worker=worker, role=role)

        user.name = name
        user.phone = phone
        user.location = location
        if role in payment_roles:
            user.online_payment_methods = ",".join(selected_payment_methods)
            user.bank_name = bank_name or None
            user.bank_account_number = bank_account_number or None
            user.demo_cardholder_name = cardholder_name or None
            user.demo_card_number = demo_card_number or None
            user.demo_card_expiry = demo_card_expiry or None
            if qr_filename:
                user.qr_code_filename = qr_filename
            elif remove_qr_code:
                user.qr_code_filename = None

        if role == "Worker":
            skill = request.form.get("skill", "").strip()
            if not 2 <= len(skill) <= 100:
                flash("Skill must contain between 2 and 100 characters.", "error")
                return render_template("edit_profile.html", user=user, worker=worker, role=role)

            try:
                rate_per_day = Decimal(request.form.get("rate_per_day", "").strip())
            except (InvalidOperation, ValueError):
                rate_per_day = Decimal("0")
            if not rate_per_day.is_finite() or rate_per_day <= 0:
                flash("Enter a valid positive daily rate.", "error")
                return render_template("edit_profile.html", user=user, worker=worker, role=role)

            try:
                image_filename = save_uploaded_image(request.files.get("image"))
            except ValueError as error:
                flash(str(error), "error")
                return render_template("edit_profile.html", user=user, worker=worker, role=role)

            if worker is None:
                legacy_matches = Worker.query.filter_by(
                    user_id=None,
                    name=previous_name,
                    phone=phone,
                ).all()
                if len(legacy_matches) == 1:
                    worker = legacy_matches[0]
                    worker.user_id = user.id
                else:
                    worker = Worker(user_id=user.id, available=True)
                    db.session.add(worker)

            worker.name = name
            worker.phone = phone
            worker.skill = skill
            worker.location = location
            worker.rate_per_day = rate_per_day
            worker.available = request.form.get("available") == "true"
            if image_filename:
                worker.image_filename = image_filename

        db.session.commit()
        session["user_name"] = user.name
        flash("Your profile has been updated.", "success")
        return redirect(url_for("profile"))

    return render_template("edit_profile.html", user=user, worker=worker, role=role)

@app.route("/workers")
def workers():

    if "user_id" not in session:
        return redirect(url_for("login"))
    search = request.args.get("search", "").strip()
    location = request.args.get("location", "").strip()
    availability = request.args.get("availability", "").strip()
    query = Worker.query
    if search:
        query = query.filter(
            db.or_(
                Worker.name.ilike(f"%{search}%"),
                Worker.skill.ilike(f"%{search}%")
            )
        )
    if location:
        query = query.filter(
            Worker.location.ilike(f"%{location}%")
        )
    if availability == "available":
        query = query.filter(
            Worker.available == True
        )

    elif availability == "unavailable":
        query = query.filter(
            Worker.available == False
        )

    worker_list = query.all()
    for worker in worker_list:
        worker.average_rating, worker.review_count = get_review_summary(
            Review.query.filter_by(worker_id=worker.id).all()
        )

    return render_template(
        "workers.html",
        workers=worker_list,
        search=search,
        location=location,
        availability=availability
    )

@app.route("/book-worker/<int:worker_id>", methods=["GET", "POST"])
def book_worker(worker_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        flash("Only farmers can book workers.", "error")
        return redirect(url_for("workers"))

    worker = Worker.query.get_or_404(worker_id)

    if request.method == "POST":
        try:
            booking_date = date.fromisoformat(request.form.get("booking_date", ""))
        except ValueError:
            return "Enter a valid booking date.", 400
        if booking_date < date.today():
            return "Booking date cannot be in the past.", 400
        if not worker.available:
            return "This worker is currently unavailable.", 409

        new_booking = Booking(
            farmer_id=session["user_id"],
            worker_id=worker.id,
            booking_date=booking_date,
            status="Pending"
        )

        db.session.add(new_booking)
        if worker.user_id:
            notify_user(
                worker.user_id,
                f"New farm work request from {session.get('user_name', 'a farmer')}.",
                "booking_request",
            )
        db.session.commit()

        flash("Worker booking request sent successfully!", "success")
        return redirect(url_for("workers"))

    return render_template(
        "book_worker.html",
        worker=worker
    )

@app.route("/my-bookings")
def my_bookings():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        return "Farmer access required.", 403

    bookings = Booking.query.filter_by(
        farmer_id=session["user_id"]
    ).all()

    return render_template(
        "my_bookings.html",
        bookings=bookings
    )

@app.route("/worker-dashboard")
def worker_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Worker":
        return "Worker access required.", 403

    worker = Worker.query.filter_by(user_id=session["user_id"]).first()
    if worker:
        worker_bookings = Booking.query.filter_by(worker_id=worker.id)
        bookings = worker_bookings.filter_by(status="Pending").all()
        accepted_bookings = worker_bookings.filter_by(status="Accepted").all()
    else:
        bookings = []
        accepted_bookings = []

    return render_template(
        "worker_dashboard.html",
        bookings=bookings,
        accepted_bookings=accepted_bookings,
        worker=worker,
    )

@app.route("/accept-booking/<int:booking_id>", methods=["POST"])
def accept_booking(booking_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    booking = Booking.query.get_or_404(booking_id)

    if session.get("user_role") != "Worker":
        return "Only workers can manage work requests.", 403
    if booking.worker.user_id and booking.worker.user_id != session["user_id"]:
        return "Unauthorized access", 403

    booking.status = "Accepted"
    notify_user(booking.farmer_id, "Your worker booking was accepted.", "booking_accepted")

    db.session.commit()

    return redirect(url_for("worker_dashboard"))

@app.route("/reject-booking/<int:booking_id>", methods=["POST"])
def reject_booking(booking_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    booking = Booking.query.get_or_404(booking_id)

    if session.get("user_role") != "Worker":
        return "Only workers can manage work requests.", 403
    if booking.worker.user_id and booking.worker.user_id != session["user_id"]:
        return "Unauthorized access", 403

    booking.status = "Rejected"
    notify_user(booking.farmer_id, "Your worker booking was rejected.", "booking_rejected")

    db.session.commit()

    return redirect(url_for("worker_dashboard"))

@app.route("/add-tractor", methods=["GET", "POST"])
def add_tractor():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        brand = request.form.get("brand", "").strip()
        location = request.form.get("location", "").strip()
        try:
            rent_per_day = float(request.form.get("rent_per_day", ""))
        except ValueError:
            flash("Enter a valid daily rent.", "error")
            return render_template("add_tractor.html", tractor=None), 400
        if not name or not brand or not location or rent_per_day <= 0:
            flash("Enter all details and a daily rent greater than zero.", "error")
            return render_template("add_tractor.html", tractor=None), 400

        try:
            image_filename = save_uploaded_image(request.files.get("image"))
        except ValueError as error:
            flash(str(error), "error")
            return render_template("add_tractor.html", tractor=None), 400

        new_tractor = Tractor(
            owner_id=session["user_id"],
            name=name,
            brand=brand,
            rent_per_day=rent_per_day,
            location=location,
            available=True,
            image_filename=image_filename,
        )

        db.session.add(new_tractor)
        db.session.commit()

        flash("Tractor added successfully!", "success")
        return redirect(url_for("add_tractor"))

    return render_template("add_tractor.html", tractor=None)


@app.route("/edit-tractor/<int:tractor_id>", methods=["GET", "POST"])
def edit_tractor(tractor_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    tractor = Tractor.query.filter_by(
        id=tractor_id,
        owner_id=session["user_id"],
    ).first_or_404()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        brand = request.form.get("brand", "").strip()
        location = request.form.get("location", "").strip()
        try:
            rent_per_day = float(request.form.get("rent_per_day", ""))
        except ValueError:
            flash("Enter a valid daily rent.", "error")
            return render_template("add_tractor.html", tractor=tractor), 400
        if not name or not brand or not location or rent_per_day <= 0:
            flash("Enter all details and a daily rent greater than zero.", "error")
            return render_template("add_tractor.html", tractor=tractor), 400

        try:
            image_filename = save_uploaded_image(request.files.get("image"))
        except ValueError as error:
            flash(str(error), "error")
            return render_template("add_tractor.html", tractor=tractor), 400

        tractor.name = name
        tractor.brand = brand
        tractor.rent_per_day = rent_per_day
        tractor.location = location
        if image_filename:
            tractor.image_filename = image_filename
        db.session.commit()
        flash("Tractor listing updated.", "success")
        return redirect(url_for("edit_tractor", tractor_id=tractor.id))

    return render_template("add_tractor.html", tractor=tractor)

@app.route("/add-machinery", methods=["GET", "POST"])
def add_machinery():

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        machinery_type = request.form.get("type", "").strip()
        location = request.form.get("location", "").strip()
        try:
            rent_per_day = float(request.form.get("rent_per_day", ""))
        except ValueError:
            flash("Enter a valid daily rent.", "error")
            return render_template("add_machinery.html", machinery_item=None), 400
        if not name or not machinery_type or not location or rent_per_day <= 0:
            flash("Enter all details and a daily rent greater than zero.", "error")
            return render_template("add_machinery.html", machinery_item=None), 400

        try:
            image_filename = save_uploaded_image(request.files.get("image"))
        except ValueError as error:
            flash(str(error), "error")
            return render_template("add_machinery.html", machinery_item=None), 400

        new_machinery = Machinery(
            owner_id=session["user_id"],
            name=name,
            type=machinery_type,
            rent_per_day=rent_per_day,
            location=location,
            available=True,
            image_filename=image_filename,
        )

        db.session.add(new_machinery)
        db.session.commit()

        flash("Agricultural machinery added successfully!", "success")
        return redirect(url_for("add_machinery"))

    return render_template("add_machinery.html", machinery_item=None)


@app.route("/edit-machinery/<int:machinery_id>", methods=["GET", "POST"])
def edit_machinery(machinery_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    machinery_item = Machinery.query.filter_by(
        id=machinery_id,
        owner_id=session["user_id"],
    ).first_or_404()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        machinery_type = request.form.get("type", "").strip()
        location = request.form.get("location", "").strip()
        try:
            rent_per_day = float(request.form.get("rent_per_day", ""))
        except ValueError:
            flash("Enter a valid daily rent.", "error")
            return render_template("add_machinery.html", machinery_item=machinery_item), 400
        if not name or not machinery_type or not location or rent_per_day <= 0:
            flash("Enter all details and a daily rent greater than zero.", "error")
            return render_template("add_machinery.html", machinery_item=machinery_item), 400

        try:
            image_filename = save_uploaded_image(request.files.get("image"))
        except ValueError as error:
            flash(str(error), "error")
            return render_template("add_machinery.html", machinery_item=machinery_item), 400

        machinery_item.name = name
        machinery_item.type = machinery_type
        machinery_item.rent_per_day = rent_per_day
        machinery_item.location = location
        if image_filename:
            machinery_item.image_filename = image_filename
        db.session.commit()
        flash("Machinery listing updated.", "success")
        return redirect(url_for("edit_machinery", machinery_id=machinery_item.id))

    return render_template("add_machinery.html", machinery_item=machinery_item)

@app.route("/tractors")
def tractors():

    if "user_id" not in session:
        return redirect(url_for("login"))
    search = request.args.get("search", "").strip()
    location = request.args.get("location", "").strip()
    max_price = request.args.get("max_price", "").strip()

    query = Tractor.query
    if search:
        query = query.filter(
            db.or_(
                Tractor.name.ilike(f"%{search}%"),
                Tractor.brand.ilike(f"%{search}%")
            )
        )
    if location:
        query = query.filter(
            Tractor.location.ilike(f"%{location}%")
        )
    if max_price:
        try:
            max_price_value = float(max_price)

            query = query.filter(
                Tractor.rent_per_day <= max_price_value
            )

        except ValueError:
            pass

    tractor_list = []
    for tractor in query.all():
        availability = get_equipment_availability(
            TractorRental,
            TractorRental.tractor_id,
            tractor.id,
            tractor.available,
        )
        if not availability["is_listed"]:
            continue
        for key, value in availability.items():
            setattr(tractor, key, value)
        tractor_list.append(tractor)

    for tractor in tractor_list:
        tractor.average_rating, tractor.review_count = get_review_summary(
            Review.query.filter_by(tractor_id=tractor.id).all()
        )

    return render_template(
        "tractors.html",
        tractors=tractor_list,
        search=search,
        location=location,
        max_price=max_price
    )

@app.route("/machinery")
def machinery():

    if "user_id" not in session:
        return redirect(url_for("login"))

    search = request.args.get("search", "").strip()
    location = request.args.get("location", "").strip()
    max_price = request.args.get("max_price", "").strip()

    query = Machinery.query
    if search:
        query = query.filter(
            db.or_(
                Machinery.name.ilike(f"%{search}%"),
                Machinery.type.ilike(f"%{search}%")
            )
        )
    if location:
        query = query.filter(
            Machinery.location.ilike(f"%{location}%")
        )
    if max_price:
        try:
            max_price_value = float(max_price)

            query = query.filter(
                Machinery.rent_per_day <= max_price_value
            )

        except ValueError:
            pass

    machinery_list = []
    for item in query.all():
        availability = get_equipment_availability(
            MachineryRental,
            MachineryRental.machinery_id,
            item.id,
            item.available,
        )
        if not availability["is_listed"]:
            continue
        for key, value in availability.items():
            setattr(item, key, value)
        machinery_list.append(item)
    for item in machinery_list:

        reviews = Review.query.filter_by(
            machinery_id=item.id
        ).all()
        item.average_rating, item.review_count = get_review_summary(reviews)

    return render_template(
        "machinery.html",
        machinery=machinery_list,
        search=search,
        location=location,
        max_price=max_price
    )

@app.route("/machinery-reviews/<int:machinery_id>")
def machinery_reviews(machinery_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    machinery = Machinery.query.get_or_404(machinery_id)

    reviews = Review.query.filter_by(
        machinery_id=machinery_id
    ).order_by(Review.id.desc()).all()
    average_rating, _ = get_review_summary(reviews)

    return render_template(
        "listing_reviews.html",
        listing=machinery,
        listing_kind="Machinery",
        reviews=reviews,
        average_rating=average_rating,
        back_url=(
            url_for("my_machinery_rentals")
            if session.get("user_role") == "Farmer"
            else url_for("machinery")
        ),
    )


@app.route("/worker-reviews/<int:worker_id>")
def worker_reviews(worker_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    worker = Worker.query.get_or_404(worker_id)
    reviews = Review.query.filter_by(worker_id=worker.id).order_by(Review.id.desc()).all()
    average_rating, _ = get_review_summary(reviews)
    return render_template(
        "listing_reviews.html",
        listing=worker,
        listing_kind="Worker",
        reviews=reviews,
        average_rating=average_rating,
        back_url=url_for("workers"),
    )


@app.route("/tractor-reviews/<int:tractor_id>")
def tractor_reviews(tractor_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    tractor = Tractor.query.get_or_404(tractor_id)
    reviews = Review.query.filter_by(tractor_id=tractor.id).order_by(Review.id.desc()).all()
    average_rating, _ = get_review_summary(reviews)
    return render_template(
        "listing_reviews.html",
        listing=tractor,
        listing_kind="Tractor",
        reviews=reviews,
        average_rating=average_rating,
        back_url=url_for("tractors"),
    )


@app.route("/review/<kind>/<int:item_id>", methods=["GET", "POST"])
def submit_listing_review(kind, item_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        return "Only farmers can submit reviews.", 403

    if kind == "worker":
        listing = Worker.query.get_or_404(item_id)
        rental_id = request.values.get("booking_id", type=int)
        if rental_id is None:
            return "Select an accepted worker booking before submitting a review.", 400
        rental = Booking.query.filter_by(
            id=rental_id,
            farmer_id=session["user_id"],
            worker_id=listing.id,
        ).first_or_404()
        existing_review = Review.query.filter_by(booking_id=rental.id).first()
        listing_name = listing.name
        target_user_id = listing.user_id
        relationship_id_field = "booking_id"
        review_data = {"worker_id": listing.id, "booking_id": rental.id}
    elif kind == "tractor":
        listing = Tractor.query.get_or_404(item_id)
        rental_id = request.values.get("rental_id", type=int)
        if rental_id is None:
            return "Select an accepted tractor rental before submitting a review.", 400
        rental = TractorRental.query.filter_by(
            id=rental_id,
            farmer_id=session["user_id"],
            tractor_id=listing.id,
        ).first_or_404()
        existing_review = Review.query.filter_by(tractor_rental_id=rental.id).first()
        listing_name = listing.name
        target_user_id = listing.owner_id
        relationship_id_field = "rental_id"
        review_data = {"tractor_id": listing.id, "tractor_rental_id": rental.id}
    else:
        abort(404)

    if rental.status not in ("Accepted", "Completed"):
        return "You can review only after an accepted booking or rental.", 403
    if existing_review:
        return "You have already reviewed this booking or rental.", 409

    if request.method == "POST":
        try:
            rating = int(request.form.get("rating", ""))
        except ValueError:
            return "Rating must be a whole number from 1 to 5.", 400
        comment = request.form.get("comment", "").strip()
        if not 1 <= rating <= 5:
            return "Rating must be between 1 and 5.", 400
        if not comment or len(comment) > 2000:
            return "Review comments must contain 1 to 2000 characters.", 400

        review = Review(
            farmer_id=session["user_id"],
            rating=rating,
            comment=comment,
            **review_data,
        )
        db.session.add(review)
        if target_user_id:
            notify_user(
                target_user_id,
                f"A new review was posted for {listing_name}.",
                "new_review",
            )
        db.session.commit()
        if kind == "worker":
            return redirect(url_for("worker_reviews", worker_id=item_id))
        return redirect(url_for("tractor_reviews", tractor_id=item_id))

    return render_template(
        "submit_listing_review.html",
        listing=listing,
        listing_kind=kind.title(),
        rental=rental,
        relationship_id_field=relationship_id_field,
    )

@app.route("/rent-machinery/<int:machinery_id>", methods=["GET", "POST"])
def rent_machinery(machinery_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        flash("Only farmers can rent machinery.", "error")
        return redirect(url_for("machinery"))

    machinery = Machinery.query.get_or_404(machinery_id)
    availability = get_equipment_availability(
        MachineryRental,
        MachineryRental.machinery_id,
        machinery.id,
        machinery.available,
    )
    if not availability["is_listed"]:
        return "This machinery is not available for rental.", 409

    if request.method == "POST":
        machinery = Machinery.query.filter_by(id=machinery.id).with_for_update().first_or_404()
        try:
            start_date, end_date = parse_rental_dates(request.form)
        except ValueError as error:
            return str(error), 400

        if rental_dates_conflict(
            MachineryRental,
            MachineryRental.machinery_id,
            machinery.id,
            start_date,
            end_date,
        ):
            return "This machinery already has a pending or accepted request for those dates.", 409

        new_rental = MachineryRental(
            farmer_id=session["user_id"],
            machinery_id=machinery.id,
            rental_date=start_date,
            start_date=start_date,
            end_date=end_date,
            status="Pending"
        )

        db.session.add(new_rental)
        notify_user(
            machinery.owner_id,
            f"New machinery rental request for {machinery.name}.",
            "machinery_request",
        )
        db.session.commit()

        flash("Machinery rental request sent successfully!", "success")
        return redirect(url_for("my_machinery_rentals"))

    return render_template(
        "rent_machinery.html",
        machinery=machinery,
        available_from=availability["available_from"].isoformat(),
    )

@app.route("/rent-tractor/<int:tractor_id>", methods=["GET", "POST"])
def rent_tractor(tractor_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        flash("Only farmers can rent tractors.", "error")
        return redirect(url_for("tractors"))

    tractor = Tractor.query.get_or_404(tractor_id)
    availability = get_equipment_availability(
        TractorRental,
        TractorRental.tractor_id,
        tractor.id,
        tractor.available,
    )
    if not availability["is_listed"]:
        return "This tractor is not available for rental.", 409

    if request.method == "POST":
        tractor = Tractor.query.filter_by(id=tractor.id).with_for_update().first_or_404()
        try:
            start_date, end_date = parse_rental_dates(request.form)
        except ValueError as error:
            return str(error), 400

        if rental_dates_conflict(
            TractorRental,
            TractorRental.tractor_id,
            tractor.id,
            start_date,
            end_date,
        ):
            return "This tractor already has a pending or accepted request for those dates.", 409

        new_rental = TractorRental(
            farmer_id=session["user_id"],
            tractor_id=tractor.id,
            rental_date=start_date,
            start_date=start_date,
            end_date=end_date,
            status="Pending"
        )

        db.session.add(new_rental)
        notify_user(
            tractor.owner_id,
            f"New tractor rental request for {tractor.name}.",
            "tractor_request",
        )
        db.session.commit()

        flash("Tractor rental request sent successfully!", "success")
        return redirect(url_for("my_tractor_rentals"))

    return render_template(
        "rent_tractor.html",
        tractor=tractor,
        available_from=availability["available_from"].isoformat(),
    )

@app.route("/my-tractor-rentals")
def my_tractor_rentals():

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        return "Farmer access required.", 403

    rentals = TractorRental.query.filter_by(
        farmer_id=session["user_id"]
    ).all()

    return render_template(
        "my_tractor_rentals.html",
        rentals=rentals
    )

@app.route("/my-machinery-rentals")
def my_machinery_rentals():

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        return "Farmer access required.", 403

    rentals = MachineryRental.query.filter_by(
        farmer_id=session["user_id"]
    ).all()

    return render_template(
        "my_machinery_rentals.html",
        rentals=rentals
    )


@app.route("/payments")
def payment_history():
    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("user_role")
    if role == "Farmer":
        payments = Payment.query.filter_by(
            farmer_id=session["user_id"]
        ).order_by(Payment.created_at.desc()).all()
    elif role == "Equipment Owner":
        payments = (
            Payment.query
            .outerjoin(TractorRental, Payment.tractor_rental_id == TractorRental.id)
            .outerjoin(MachineryRental, Payment.machinery_rental_id == MachineryRental.id)
            .outerjoin(Tractor, TractorRental.tractor_id == Tractor.id)
            .outerjoin(Machinery, MachineryRental.machinery_id == Machinery.id)
            .filter(db.or_(
                Tractor.owner_id == session["user_id"],
                Machinery.owner_id == session["user_id"],
            ))
            .order_by(Payment.created_at.desc())
            .all()
        )
    elif role == "Worker":
        worker = Worker.query.filter_by(user_id=session["user_id"]).first()
        payments = (
            Payment.query.join(Booking, Payment.booking_id == Booking.id)
            .filter(Booking.worker_id == worker.id)
            .order_by(Payment.created_at.desc())
            .all()
            if worker else []
        )
    else:
        return "Payment history is not available for this account.", 403

    successful_total = sum(
        (payment.amount for payment in payments if payment.payment_status == "Successful"),
        Decimal("0.00"),
    )
    return render_template(
        "payments.html",
        payments=payments,
        successful_total=successful_total,
        role=role,
    )


@app.route("/payments/<int:payment_id>")
def payment_details(payment_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    payment = Payment.query.get_or_404(payment_id)
    user_id = session["user_id"]
    role = session.get("user_role")
    if role == "Farmer":
        authorized = payment.farmer_id == user_id
    elif role == "Equipment Owner":
        authorized = bool(
            (payment.tractor_rental and payment.tractor_rental.tractor.owner_id == user_id)
            or (payment.machinery_rental and payment.machinery_rental.machinery.owner_id == user_id)
        )
    elif role == "Worker":
        authorized = bool(payment.booking and payment.booking.worker.user_id == user_id)
    else:
        authorized = False

    if not authorized:
        abort(404)

    return render_template("payment_details.html", payment=payment)


@app.route("/payment/<kind>/<int:rental_id>", methods=["GET", "POST"])
def start_payment(kind, rental_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        return "Payments are available to farmers only.", 403

    rental = None
    booking = None
    if kind == "tractor":
        rental = TractorRental.query.filter_by(
            id=rental_id,
            farmer_id=session["user_id"],
        ).first_or_404()
        item = rental.tractor
        payment = Payment.query.filter_by(tractor_rental_id=rental.id).first()
    elif kind == "machinery":
        rental = MachineryRental.query.filter_by(
            id=rental_id,
            farmer_id=session["user_id"],
        ).first_or_404()
        item = rental.machinery
        payment = Payment.query.filter_by(machinery_rental_id=rental.id).first()
    elif kind == "worker":
        booking = Booking.query.filter_by(
            id=rental_id,
            farmer_id=session["user_id"],
        ).first_or_404()
        item = booking.worker
        payment = Payment.query.filter_by(booking_id=booking.id).first()
        if booking.status != "Accepted":
            return "Payment is available after the worker accepts the booking.", 403
        if item.rate_per_day is None or item.rate_per_day <= 0:
            return "This worker has not set a daily rate yet.", 409
    else:
        return "Unknown rental type.", 404

    if rental and rental.status not in ("Accepted", "Completed"):
        return "Payment is available after the owner accepts the rental.", 403

    if booking:
        amount_due = Decimal(booking.worker.rate_per_day)
        payment_recipient = booking.worker.user
    else:
        rental_start = rental.start_date or rental.rental_date
        rental_end = rental.end_date or rental_start
        amount_due = Decimal(str(item.rent_per_day)) * ((rental_end - rental_start).days + 1)
        payment_recipient = item.owner
    online_payment_methods = (
        payment_recipient.available_online_payment_methods
        if payment_recipient else []
    )
    payment_method_labels = {
        "net_banking": "Net Banking",
        "debit_card": "Debit Card",
        "qr_code": "QR Code",
    }

    if request.method == "POST":
        selected_method = request.form.get("payment_method", "").strip().lower()
        if selected_method == "cash":
            payment_method = "Cash"
        elif selected_method == "upi":
            selected_online_method = request.form.get("online_method", "").strip().lower()
            if selected_online_method not in online_payment_methods:
                return "Choose an online payment option enabled by the worker or equipment owner.", 400
            payment_method = payment_method_labels[selected_online_method]
        else:
            return "Choose a valid payment method.", 400

        outcome = request.form.get("outcome", "").title()
        if outcome not in {"Pending", "Successful", "Failed"}:
            return "Choose a valid payment outcome.", 400
        if payment and payment.payment_status == "Successful":
            return "This rental has already been paid.", 409

        if payment is None:
            if booking:
                payment = Payment(
                    farmer_id=session["user_id"],
                    booking_id=booking.id,
                    amount=amount_due,
                    payment_method=payment_method,
                )
            else:
                payment = Payment(
                    farmer_id=session["user_id"],
                    tractor_rental_id=rental.id if kind == "tractor" else None,
                    machinery_rental_id=rental.id if kind == "machinery" else None,
                    amount=amount_due,
                    payment_method=payment_method,
                )
            db.session.add(payment)

        payment.payment_status = outcome
        payment.payment_method = payment_method
        payment.transaction_id = (
            f"TXN-{uuid.uuid4().hex}" if outcome != "Pending" else None
        )
        if outcome == "Successful" and booking and booking.worker.user_id:
            notify_user(
                booking.worker.user_id,
                f"{session.get('user_name', 'A farmer')} paid for your worker booking.",
                "payment_received",
            )
        db.session.commit()
        flash(f"Payment status: {outcome}.", "success" if outcome == "Successful" else "error")
        return redirect(url_for("start_payment", kind=kind, rental_id=rental_id))

    return render_template(
        "payment_demo.html",
        kind=kind,
        rental=rental,
        booking=booking,
        item=item,
        amount_due=amount_due,
        payment=payment,
        payment_recipient=payment_recipient,
        online_payment_methods=online_payment_methods,
    )

@app.route("/machinery-rental-details/<int:rental_id>")
def machinery_rental_details(rental_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Farmer":
        return "Farmer access required.", 403

    rental = MachineryRental.query.get_or_404(rental_id)
    if rental.farmer_id != session["user_id"]:
        return "Unauthorized access", 403

    return render_template(
        "machinery_rental_details.html",
        rental=rental
    )

@app.route("/owner-rentals")
def owner_rentals():

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    owner_id = session["user_id"]

    rentals = (
        TractorRental.query
        .join(Tractor, TractorRental.tractor_id == Tractor.id)
        .filter(Tractor.owner_id == owner_id)
        .all()
    )

    return render_template(
        "owner_rentals.html",
        rentals=rentals
    )

@app.route("/owner-machinery-rentals")
def owner_machinery_rentals():

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    owner_id = session["user_id"]

    rentals = (
        MachineryRental.query
        .join(Machinery, MachineryRental.machinery_id == Machinery.id)
        .filter(Machinery.owner_id == owner_id)
        .all()
    )

    return render_template(
        "owner_machinery_rentals.html",
        rentals=rentals
    )

@app.route("/owner-rental-details/<kind>/<int:rental_id>")
def owner_rental_details(kind, rental_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        abort(404)

    owner_id = session["user_id"]
    if kind == "tractor":
        rental = (
            TractorRental.query
            .join(Tractor, TractorRental.tractor_id == Tractor.id)
            .filter(TractorRental.id == rental_id, Tractor.owner_id == owner_id)
            .first_or_404()
        )
        item = rental.tractor
        accept_endpoint = "accept_tractor_rental"
        reject_endpoint = "reject_tractor_rental"
        list_endpoint = "owner_rentals"
        item_type = "Tractor"
    elif kind == "machinery":
        rental = (
            MachineryRental.query
            .join(Machinery, MachineryRental.machinery_id == Machinery.id)
            .filter(MachineryRental.id == rental_id, Machinery.owner_id == owner_id)
            .first_or_404()
        )
        item = rental.machinery
        accept_endpoint = "accept_machinery_rental"
        reject_endpoint = "reject_machinery_rental"
        list_endpoint = "owner_machinery_rentals"
        item_type = "Machinery"
    else:
        abort(404)

    return render_template(
        "owner_rental_details.html",
        rental=rental,
        item=item,
        kind=kind,
        item_type=item_type,
        accept_endpoint=accept_endpoint,
        reject_endpoint=reject_endpoint,
        list_endpoint=list_endpoint,
    )

@app.route("/accept-machinery-rental/<int:rental_id>", methods=["POST"])
def accept_machinery_rental(rental_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    rental = MachineryRental.query.get_or_404(rental_id)
    if rental.machinery.owner_id != session["user_id"]:
        return "Unauthorized access", 403

    if rental.status != "Accepted":
        notify_user(
        rental.farmer_id,
        f"Your machinery rental for {rental.machinery.name} was accepted.",
        "machinery_accepted",
        )
    rental.status = "Accepted"

    db.session.commit()

    return redirect(url_for("owner_machinery_rentals"))

@app.route("/reject-machinery-rental/<int:rental_id>", methods=["POST"])
def reject_machinery_rental(rental_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    rental = MachineryRental.query.get_or_404(rental_id)
    if rental.machinery.owner_id != session["user_id"]:
        return "Unauthorized access", 403

    if rental.status != "Rejected":
        notify_user(
        rental.farmer_id,
        f"Your machinery rental for {rental.machinery.name} was rejected.",
        "machinery_rejected",
        )
    rental.status = "Rejected"

    db.session.commit()

    return redirect(url_for("owner_machinery_rentals"))

@app.route("/review-machinery/<int:machinery_id>", methods=["GET", "POST"])
def review_machinery(machinery_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Farmer":
        return "Only farmers can review machinery.", 403

    machinery = Machinery.query.get_or_404(machinery_id)
    rental_id = request.values.get("rental_id", type=int)
    if rental_id is None:
        return "Select an accepted rental before submitting a review.", 400

    rental = MachineryRental.query.filter_by(
        id=rental_id,
        farmer_id=session["user_id"],
        machinery_id=machinery.id,
    ).first_or_404()

    if rental.status not in ("Accepted", "Completed"):
        return "You can review machinery only after an accepted rental.", 403

    existing_review = Review.query.filter_by(rental_id=rental.id).first()
    if existing_review:
        return "You have already reviewed this rental.", 409

    if request.method == "POST":
        try:
            rating = int(request.form.get("rating", ""))
        except ValueError:
            return "Rating must be a whole number from 1 to 5.", 400

        comment = request.form.get("comment", "").strip()
        if rating < 1 or rating > 5:
            return "Rating must be between 1 and 5."
        if not comment or len(comment) > 2000:
            return "Review comments must contain 1 to 2000 characters.", 400

        new_review = Review(
            farmer_id=session["user_id"],
            machinery_id=machinery.id,
            rental_id=rental.id,
            rating=rating,
            comment=comment
        )

        db.session.add(new_review)
        notify_user(
            machinery.owner_id,
            f"A new review was posted for {machinery.name}.",
            "new_review",
        )
        db.session.commit()

        return redirect(url_for("machinery_reviews", machinery_id=machinery.id))

    return render_template(
        "submit_listing_review.html",
        listing=machinery,
        listing_kind="Machinery",
        rental=rental,
        relationship_id_field="rental_id",
    )

@app.route("/accept-tractor-rental/<int:rental_id>", methods=["POST"])
def accept_tractor_rental(rental_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    rental = TractorRental.query.get_or_404(rental_id)
    if rental.tractor.owner_id != session["user_id"]:
        return "Unauthorized access", 403

    if rental.status != "Accepted":
        notify_user(
        rental.farmer_id,
        f"Your tractor rental for {rental.tractor.name} was accepted.",
        "tractor_accepted",
        )
    rental.status = "Accepted"

    db.session.commit()

    return redirect(url_for("owner_rentals"))

@app.route("/reject-tractor-rental/<int:rental_id>", methods=["POST"])
def reject_tractor_rental(rental_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403

    rental = TractorRental.query.get_or_404(rental_id)
    if rental.tractor.owner_id != session["user_id"]:
        return "Unauthorized access", 403
    if rental.status != "Rejected":
        notify_user(
        rental.farmer_id,
        f"Your tractor rental for {rental.tractor.name} was rejected.",
        "tractor_rejected",
        )
    rental.status = "Rejected"

    db.session.commit()

    return redirect(url_for("owner_rentals"))

@app.route("/equipment-dashboard")
def equipment_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Equipment Owner":
        return "Equipment owner access required.", 403
    return redirect(url_for("dashboard"))


def current_user_is_admin():
    if "user_id" not in session:
        return False
    user = db.session.get(User, session["user_id"])
    return user is not None and user.role == "Admin"


@app.route("/admin/dashboard")
def admin_dashboard():
    if not current_user_is_admin():
        return "Admin access required.", 403

    users = User.query.order_by(User.id.desc()).all()
    workers = Worker.query.order_by(Worker.id.desc()).all()
    tractors = Tractor.query.order_by(Tractor.id.desc()).all()
    machinery_items = Machinery.query.order_by(Machinery.id.desc()).all()
    bookings = Booking.query.order_by(Booking.id.desc()).all()
    tractor_rentals = TractorRental.query.order_by(TractorRental.id.desc()).all()
    machinery_rentals = MachineryRental.query.order_by(MachineryRental.id.desc()).all()
    reviews = Review.query.order_by(Review.id.desc()).all()
    payments = Payment.query.order_by(Payment.created_at.desc()).all()

    request_statuses = [booking.status for booking in bookings]
    request_statuses.extend(rental.status for rental in tractor_rentals)
    request_statuses.extend(rental.status for rental in machinery_rentals)
    stats = {
        "total_users": len(users),
        "farmers": sum("Farmer" in user.account_roles for user in users),
        "workers": sum("Worker" in user.account_roles for user in users),
        "owners": sum("Equipment Owner" in user.account_roles for user in users),
        "worker_listings": len(workers),
        "tractors": len(tractors),
        "machinery": len(machinery_items),
        "bookings": len(request_statuses),
        "pending": request_statuses.count("Pending"),
        "accepted": request_statuses.count("Accepted"),
        "rejected": request_statuses.count("Rejected"),
        "reviews": len(reviews),
        "payments": len(payments),
        "successful_payments": sum(
            (payment.amount for payment in payments if payment.payment_status == "Successful"),
            Decimal("0.00"),
        ),
    }
    return render_template(
        "admin_dashboard.html",
        stats=stats,
        users=users,
        workers=workers,
        tractors=tractors,
        machinery_items=machinery_items,
        bookings=bookings,
        tractor_rentals=tractor_rentals,
        machinery_rentals=machinery_rentals,
        reviews=reviews,
        payments=payments,
    )


@app.route("/admin/records/<section>")
def admin_records(section):
    if not current_user_is_admin():
        return "Admin access required.", 403

    section_details = {
        "users": ("Users", "Registered accounts and roles"),
        "workers": ("Workers", "Worker listings and availability"),
        "tractors": ("Tractors", "Tractor listings and rental rates"),
        "machinery": ("Machinery", "Machinery listings and rental rates"),
        "worker-bookings": ("Worker bookings", "Farmer-to-worker booking requests"),
        "tractor-rentals": ("Tractor rentals", "Tractor rental requests and status"),
        "machinery-rentals": ("Machinery rentals", "Machinery rental requests and status"),
        "reviews": ("Reviews", "Farmer feedback and ratings"),
        "payments": ("Payments", "Transactions and payment status"),
    }
    if section not in section_details:
        abort(404)

    query_by_section = {
        "users": lambda: User.query.order_by(User.id.desc()).all(),
        "workers": lambda: Worker.query.order_by(Worker.id.desc()).all(),
        "tractors": lambda: Tractor.query.order_by(Tractor.id.desc()).all(),
        "machinery": lambda: Machinery.query.order_by(Machinery.id.desc()).all(),
        "worker-bookings": lambda: Booking.query.order_by(Booking.id.desc()).all(),
        "tractor-rentals": lambda: TractorRental.query.order_by(TractorRental.id.desc()).all(),
        "machinery-rentals": lambda: MachineryRental.query.order_by(MachineryRental.id.desc()).all(),
        "reviews": lambda: Review.query.order_by(Review.id.desc()).all(),
        "payments": lambda: Payment.query.order_by(Payment.created_at.desc()).all(),
    }
    records = query_by_section[section]()
    title, description = section_details[section]
    return render_template(
        "admin_records.html",
        section=section,
        title=title,
        description=description,
        records=records,
    )


@app.route("/admin/reviews/<int:review_id>/delete", methods=["POST"])
def admin_delete_review(review_id):
    if not current_user_is_admin():
        return "Admin access required.", 403

    review = Review.query.get_or_404(review_id)
    db.session.delete(review)
    db.session.commit()
    flash("Review removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/workers/<int:worker_id>/delete", methods=["POST"])
def admin_delete_worker(worker_id):
    if not current_user_is_admin():
        return "Admin access required.", 403

    worker = Worker.query.get_or_404(worker_id)
    if worker.bookings:
        return "Workers with booking history cannot be deleted.", 409
    db.session.delete(worker)
    db.session.commit()
    flash("Worker listing removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/equipment/<kind>/<int:item_id>/delete", methods=["POST"])
def admin_delete_equipment(kind, item_id):
    if not current_user_is_admin():
        return "Admin access required.", 403

    if kind == "tractor":
        item = Tractor.query.get_or_404(item_id)
    elif kind == "machinery":
        item = Machinery.query.get_or_404(item_id)
    else:
        return "Unknown equipment type.", 404

    if item.rentals:
        return "Equipment with rental history cannot be deleted.", 409
    db.session.delete(item)
    db.session.commit()
    flash("Equipment listing removed.", "success")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    app.run(debug=True)