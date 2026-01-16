from flask import Flask, render_template, request,  redirect, url_for, session, flash, send_from_directory,send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime,timedelta, date
from functools import wraps
from sqlalchemy import func # Required for calculating sums
from calendar import monthrange # Required for calculating month boundaries
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import os
from flask import render_template, request, redirect, url_for, session, flash, send_file
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

#use other .py code  to run in this file(if file name utils)
#from utils import * 

#asasa


app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/images/')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# You might want to ensure the folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

#for add_menu item img upload
UPLOAD_FOLDER = 'static/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# A simple function to check if the file extension is allowed (optional but recommended)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'db2.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {"check_same_thread": False}
}
app.config['SECRET_KEY'] = 'super_secret_key'

db = SQLAlchemy(app)

# -------------------- DECORATORS --------------------
def admin_required(f):
    """Decorator to restrict access to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'is_admin' not in session or not session['is_admin']:
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def only_user(f):
    """Decorator to restrict access to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'is_admin' in session or session['is_admin']:
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function
# ----------------------------------------------------


# -------------------- MODELS --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, default=0.0)
    description = db.Column(db.String(255))
    image = db.Column(db.String(255))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    food_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(255))
    mobile = db.Column(db.String(15))
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    # Added status for a realistic order workflow
    status = db.Column(db.String(50), default='Pending')

class Revenue(db.Model):
    """Stores aggregated monthly financial data."""
    id = db.Column(db.Integer, primary_key=True)
    # Format: YYYY-MM
    month_year = db.Column(db.String(7), unique=True, nullable=False) 
    total_revenue = db.Column(db.Float, default=0.0)
    # Total profit is zero until calculated/updated manually via admin input
    total_profit = db.Column(db.Float, default=0.0)
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow)
# ------------------------------------------------


# -------------------- P&L UTILITY FUNCTIONS --------------------
def calculate_and_save_monthly_revenue(monthly_profit):
    """Calculates and stores total revenue and profit for the current month."""
    now = datetime.utcnow()
    month_year_str = now.strftime('%Y-%m')
    
    # Calculate the first and last day of the current month
    first_day_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Get the last day of the month using calendar.monthrange
    last_day = monthrange(now.year, now.month)[1]
    last_day_of_month = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

    # 1. Calculate Total Revenue from all orders this month
    monthly_revenue = db.session.query(func.sum(Order.total)).filter(
        Order.date_created >= first_day_of_month,
        Order.date_created <= last_day_of_month
    ).scalar() or 0.0

    # 2. Retrieve or create the Revenue record for the current month
    revenue_record = Revenue.query.filter_by(month_year=month_year_str).first()

    if not revenue_record:
        revenue_record = Revenue(month_year=month_year_str)
        db.session.add(revenue_record)
    
    # 3. Update the record
    revenue_record.total_revenue = monthly_revenue
    # *** ADDED: Save the monthly profit calculated in profit_loss route ***
    revenue_record.total_profit = monthly_profit 
    # *******************************************************************
    revenue_record.date_recorded = datetime.utcnow() # Update the last updated time

    try:
        db.session.commit()
        return monthly_revenue
    except Exception as e:
        db.session.rollback()
        print(f"Error saving monthly revenue: {e}")
        return 0.0

# -------------------- ROUTES --------------------
@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('food'))
    # NOTE: You need to create an index.html template for the home page
    return render_template('index.html')

@app.route('/static/images/<filename>')
def uploaded_file(filename):
    """Serve the files from the configured UPLOAD_FOLDER."""
    # This route uses the UPLOAD_FOLDER defined in the config to send the file.
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if not username or not email or not password:
            flash("All fields are required", "danger")
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        user = User(username=username, email=email, password=hashed_pw)
        db.session.add(user)
        try:
            db.session.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login'))
        except Exception:
            flash("Username or Email already exists.", "danger")
            db.session.rollback()

    # NOTE: You need to create a register.html template
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash(f"Welcome {user.username}!", "success")
            return redirect(url_for('admin_dashboard' if user.is_admin else 'food'))
        else:
            flash("Invalid credentials!", "danger")
    
    # NOTE: You need to create a login.html template
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("You have logged out successfully.", "info")
    return redirect(url_for('login'))

@app.route('/about')
def about():
    return render_template("about.html")


@app.route('/food', methods=['GET', 'POST'])
def food():
    if 'username' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))
 
    foods = Food.query.all()
    # POST handling for ordering is now moved to the specific /order_item route
    current_cart = get_cart()
    
    # NOTE: You need to create a food.html template
    return render_template('food.html', foods=foods, username=session['username'], cart=current_cart)


@app.route('/order_item/<int:food_id>', methods=['GET', 'POST'])
def order_item(food_id):
    if 'username' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    food = Food.query.get_or_404(food_id)

    if request.method == 'POST':
        try:
            quantity = int(request.form['quantity'])
            location = request.form['location']
            mobile = request.form['mobile']

            if quantity <= 0:
                flash("Quantity must be at least 1.", "danger")
                return redirect(url_for('order_item', food_id=food_id))

            total = quantity * food.price

            # Save order
            new_order = Order(
                user_id=session['user_id'],
                food_name=food.name,
                quantity=quantity,
                price=food.price,
                total=total,
                location=location,
                mobile=mobile
            )
            db.session.add(new_order)
            db.session.commit()

            # -------------------- PDF GENERATION --------------------
            buffer = BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=letter)

            # Title
            pdf.setFont("Helvetica-Bold", 20)
            pdf.drawCentredString(300, 770, "ORDER RECEIPT")

            # Customer details
            pdf.setFont("Helvetica", 12)
            y = 730
            pdf.drawString(50, y, f"Customer Name: {session['username']}")
            y -= 20
            pdf.drawString(50, y, f"Mobile: {mobile}")
            y -= 20
            pdf.drawString(50, y, f"Delivery Location: {location}")
            y -= 20
            pdf.drawString(50, y, f"Order Date: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}")
            

            # Food details table
            y -= 50
            from reportlab.platypus import Table, TableStyle
            from reportlab.lib import colors

            table_data = [
                ["Item Name", "Qty", "Price (unit price)", "Total (rupees)"],
                [food.name, str(quantity), str(food.price), str(total)]
            ]

            table = Table(table_data, colWidths=[200, 60, 100, 100])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ]))

            table.wrapOn(pdf, 50, y)
            table.drawOn(pdf, 50, y - 60)

            # Grand Total
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(50, y - 90, f"final Bill: {total}/-")

            # Footer
            pdf.setFont("Helvetica", 10)
            pdf.drawString(50, y - 120, "Thank you for ordering with Foodie Haven!")

            pdf.save()
            buffer.seek(0)

            return send_file(
                buffer,
                as_attachment=True,
                download_name="Order_Receipt.pdf",
                mimetype='application/pdf'
            )

        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")

    return render_template('order_item.html', food=food, username=session['username'])


@app.route('/orders')
def orders():
    if 'username' not in session:
        return redirect(url_for('login'))

    user_orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.date_created.desc()).all()
    # NOTE: You need to create an orders.html template
    return render_template('orders.html', orders=user_orders, username=session['username'])

from datetime import datetime, timedelta

@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    # Security check (already in your code)
    if 'is_admin' not in session or not session['is_admin']:
        flash("Access denied.", "danger")
        return redirect(url_for('login'))

    # Time-based calculations
    now = datetime.utcnow()
    today_start = datetime.combine(now.date(), datetime.min.time())
    week_start = today_start - timedelta(days=now.weekday()) # Monday of current week

    # 1. Today's Orders
    today_orders = Order.query.filter(Order.date_created >= today_start).order_by(Order.date_created.desc()).all()
    
    # 2. This Week's Orders (excluding today to avoid duplicates)
    week_orders = Order.query.filter(Order.date_created >= week_start, Order.date_created < today_start).order_by(Order.date_created.desc()).all()
    
    # 3. Older Orders
    older_orders = Order.query.filter(Order.date_created < week_start).order_by(Order.date_created.desc()).all()

    users = User.query.all()
    
    return render_template(
        'admin_dashboard.html', 
        users=users, 
        today_orders=today_orders,
        week_orders=week_orders,
        older_orders=older_orders,
        total_count=len(today_orders) + len(week_orders) + len(older_orders)
    )# -----------------------------------------------

# ------------------------------------------------
@app.route('/profit_loss')
@admin_required
def profit_loss():
    # --- 1. Date Filtering Logic ---
    time_frame = request.args.get('time_frame', 'monthly') # Default to monthly for better UX
    
    today = datetime.utcnow().date()
    start_date = None
    end_date = None
    
    if time_frame == 'daily':
        start_date = datetime.combine(today, datetime.min.time())
        end_date = datetime.combine(today, datetime.max.time())
    elif time_frame == 'weekly':
        start_of_week_date = today - timedelta(days=today.weekday())
        end_date = datetime.combine(start_of_week_date + timedelta(days=6), datetime.max.time())
        start_date = datetime.combine(start_of_week_date, datetime.min.time())
    elif time_frame == 'monthly':
        first_day = today.replace(day=1)
        last_day = monthrange(today.year, today.month)[1]
        start_date = datetime.combine(first_day, datetime.min.time())
        end_date = datetime.combine(today.replace(day=last_day), datetime.max.time())

    # 2. Date Filter
    date_filter = [Order.date_created >= start_date, Order.date_created <= end_date] if start_date else [1 == 0]

    # 3. Query Results
    results = db.session.query(
        Food.id,
        Food.name.label('item_name'),
        Food.cost.label('abandoned_cost'),
        Food.price.label('selling_price'),
        func.sum(Order.quantity).label('total_quantity'),
        (func.sum(Order.quantity) * Food.cost).label('total_cost'),
        func.sum(Order.total).label('total_selling'),
        (func.sum(Order.total) - (func.sum(Order.quantity) * Food.cost)).label('profit_loss')
    ).outerjoin(Order, Food.name == Order.food_name).filter(*date_filter).group_by(Food.id, Food.name, Food.cost, Food.price).all()

    # 4. Process Data
    data = []
    total_cost = 0.0
    total_selling = 0.0
    total_profit = 0.0
    
    for r in results:
        qty = r.total_quantity or 0
        item_selling = r.total_selling or 0.0
        item_cost = r.total_cost or 0.0
        
        data.append({
            'item_name': r.item_name,
            'abandoned_cost': r.abandoned_cost,
            'selling_price': r.selling_price,
            'total_quantity': qty,
            'total_cost': item_cost,
            'total_selling': item_selling,
            'profit_loss': r.profit_loss or 0.0,
        })
        total_cost += item_cost
        total_selling += item_selling
        total_profit += (r.profit_loss or 0.0)

    # 5. FIXED: Update Monthly Revenue Table
    # We pass BOTH revenue and profit to ensure the record updates correctly
    current_month_str = today.strftime('%Y-%m')
    update_monthly_stats(current_month_str, total_selling, total_profit)

    # 6. Retrieve reports
    monthly_reports = Revenue.query.order_by(Revenue.month_year.desc()).all()

    return render_template('profit_loss.html', rows=data, total_cost=total_cost, 
                           total_selling=total_selling, total_profit=total_profit, 
                           monthly_reports=monthly_reports, time_frame=time_frame,
                           start_date=start_date.strftime('%Y-%m-%d'), 
                           end_date=end_date.strftime('%Y-%m-%d'))

# Helper function to handle the Database Upsert (Update or Insert)
def update_monthly_stats(month_str, revenue, profit):
    report = Revenue.query.filter_by(month_year=month_str).first()
    if report:
        # Update existing record with latest calculations
        report.total_revenue = revenue
        report.total_profit = profit
        report.date_recorded = datetime.utcnow()
    else:
        # Create new record for the new month
        new_report = Revenue(month_year=month_str, total_revenue=revenue, 
                             total_profit=profit, date_recorded=datetime.utcnow())
        db.session.add(new_report)
    db.session.commit()

@app.route('/Add_menu', methods=['GET', 'POST'])
def Add_menu():
    if request.method == 'POST':
        Food_name = request.form['foodname']
        Food_price = request.form['foodprice']
        description = request.form['fooddec']
        Food_cost = request.form['foodcost']

        # 1. Get the file from the request
        if 'foodimage' not in request.files:
            flash("Image file is missing.", "danger")
            return redirect(url_for('Add_menu'))

        file = request.files['foodimage']

        # 2. Basic validation checks
        if not Food_name or not Food_price or not description or not Food_cost:
            flash("All text fields are required", "danger")
            return redirect(url_for('Add_menu'))
        
        # 3. Check if a file was selected
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(url_for('Add_menu'))

        # 4. Process the file
        if file: # and allowed_file(file.filename): # uncomment if you added the allowed_file function
            # Use secure_filename to clean the filename
            filename = secure_filename(file.filename)
            # Save the file to the configured upload folder
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            # The string to be saved in the 'image' column is the filename itself
            image_filename = filename

            # 5. Add to the database, including the image filename
            # NOTE: I am assuming your Food model has a column named 'image'
            add_menu = Food(
                name=Food_name, 
                price=Food_price, 
                description=description, 
                cost=Food_cost,
                image=image_filename # <--- THIS IS THE KEY CHANGE
            )
            db.session.add(add_menu)
            db.session.commit() # Don't forget to commit the session
            
            flash(f"Menu item {Food_name} is added successfully with image {image_filename}", "success")
            return redirect(url_for('Add_menu'))
        
        # Fallback for file error (e.g., if extension is not allowed)
        flash("File upload failed or file type not allowed.", "danger")
        return redirect(url_for('Add_menu'))
        
    return render_template('Add_menu.html')
#for cart item

def get_cart():
    """Retrieves the cart from the session, initializing it if necessary."""
    if 'cart' not in session:
        # Cart is a dictionary: {food_id: {'id': food_id, 'name': name, 'price': price, 'quantity': quantity}}
        session['cart'] = {}
    return session['cart']

def save_cart(cart):
    """Saves the cart back to the session."""
    session['cart'] = cart
    session.modified = True

@app.route('/add_to_cart/<int:food_id>')
def add_to_cart(food_id):
    if 'username' not in session:
        flash("Please log in first to add items to the cart.", "warning")
        return redirect(url_for('login'))

    food = Food.query.get_or_404(food_id)
    cart = get_cart()

    if str(food_id) in cart:
        # Item is already in cart, increment quantity
        cart[str(food_id)]['quantity'] += 1
        flash(f"{food.name} quantity updated in cart!", "info")
    else:
        # Add new item to cart
        cart[str(food_id)] = {
            'id': food.id,
            'name': food.name,
            'price': food.price,
            'quantity': 1
        }
        flash(f"{food.name} added to cart!", "success")
    
    save_cart(cart)
    return redirect(request.referrer or url_for('food'))


@app.route('/remove_from_cart/<int:food_id>')
@app.route('/remove_from_cart/<int:food_id>/<string:next_page>')
def remove_from_cart(food_id, next_page='cart'): # Defaulting redirect to 'cart' for better UX
    if 'username' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    cart = get_cart()
    food_id_str = str(food_id)

    if food_id_str in cart:
        food_name = cart[food_id_str]['name']
        current_quantity = cart[food_id_str]['quantity']
        
        # LOGIC CHANGE: Decrement quantity if > 1, otherwise remove
        if current_quantity > 1:
            cart[food_id_str]['quantity'] -= 1
            flash(f"Quantity of {food_name} reduced to {cart[food_id_str]['quantity']}.", "info")
        else:
            # If quantity is 1, completely remove the item
            del cart[food_id_str]
            flash(f"{food_name} completely removed from cart.", "warning")
            
        save_cart(cart)
    return redirect(request.referrer or url_for('food'))


from flask import render_template, session, redirect, url_for, flash
# You'll need to ensure 'app' and 'get_cart' are defined correctly elsewhere


@app.route('/cart')
def cart_view():
    if 'username' not in session:
        flash("Please log in to view your cart.", "warning")
        return redirect(url_for('login'))
    
    current_cart = get_cart()
    
    grand_total = 0.0
    
    # Loop through the cart items and calculate the total in Python
    for item_id, item_data in current_cart.items():
        price_data = item_data.get('price', 0.0)
        quantity_data = item_data.get('quantity', 0)
        
        try:
            # 1. Ensure it is a string so we can use .replace()
            price_str = str(price_data)
            
            # 2. Clean the string (removes '₹' and commas)
            price_clean = price_str.replace('₹', '').replace(',', '').strip()
            
            # 3. Final conversion to number
            price = float(price_clean)
            
            # Quantity conversion
            quantity = int(str(quantity_data))
            
            # 🟢 FIX 1: Update the item data with the cleaned, numeric values.
            # This ensures both the Python summation and Jinja multiplication use clean numbers.
            item_data['price'] = price
            item_data['quantity'] = quantity
            
            # Calculate the subtotal and add it to the grand total
            subtotal = price * quantity
            
            # 🟢 FIX 2: This is the critical line that was likely skipped by the 'except' block.
            grand_total += subtotal
            
            # Store subtotal back for potential template use
            item_data['subtotal'] = subtotal 
            
        except (ValueError, TypeError) as e:
            # If conversion fails, log the error and skip this item's calculation
            print(f"Error processing item {item_id}. Price or Quantity data is invalid: {e}")
            
    # 3. Pass BOTH the cart and the calculated grand_total to the template
    return render_template('cart.html', 
                            cart=current_cart, 
                            username=session['username'],
                            grand_total=grand_total)


# app.py (Ensure this version is what you are using for the checkout route)

# ... (rest of your app.py)

# ... (The rest of app.py remains the same until checkout route)
# app.py

# ... (Previous code remains the same)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'username' not in session:
        return redirect(url_for('login'))

    current_cart = get_cart()
    if not current_cart:
        return redirect(url_for('food'))

    # ---------------- CALCULATE TOTAL ----------------
    grand_total = 0.0
    for item_id, item_data in current_cart.items():

        # Convert price "₹120" → 120.0
        price_str = str(item_data.get('price', '0')).replace('₹', '').replace(',', '').strip()
        price = float(price_str) if price_str else 0.0

        quantity = int(item_data.get('quantity', 1))

        item_data['subtotal'] = price * quantity
        grand_total += item_data['subtotal']

    order_summary = ", ".join([f"{item['name']}({item['quantity']})" for item in current_cart.values()])


    # ---------------- CONFIRM ORDER (POST) ----------------
    if request.method == 'POST':
        location = request.form.get('location')
        mobile = request.form.get('mobile')

        if not location or not mobile:
            flash("Delivery Location and Mobile Number are required.", "danger")
            return render_template('checkout.html',
                                   cart=current_cart,
                                   grand_total=grand_total,
                                   order_summary=order_summary)

        try:
            # Save each item in database
            for item_id, item_data in current_cart.items():
                db.session.add(Order(
                    user_id=session['user_id'],
                    food_name=item_data['name'],
                    quantity=int(item_data['quantity']),
                    price=float(str(item_data['price']).replace('₹', '').strip()),
                    total=item_data['subtotal'],
                    location=location,
                    mobile=mobile
                ))

            db.session.commit()

            # Clear cart
            session.pop('cart', None)

            # ---------------- PDF Receipt ----------------
            buffer = BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=letter)
            
            # Title
            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawCentredString(300, 770, "ORDER RECEIPT")
            
            pdf.setFont("Helvetica", 12)
            y = 730
            pdf.drawString(50, y, f"Customer Name: {session['username']}")
            y -= 20
            pdf.drawString(50, y, f"Mobile: {mobile}")
            y -= 20
            pdf.drawString(50, y, f"Delivery Location: {location}")
            y -= 20
            pdf.drawString(50, y, f"Order Date: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}")
            
            # ----------- TABLE DESIGN ------------
            from reportlab.platypus import Table, TableStyle
            from reportlab.lib import colors
            
            y -= 40
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(50, y, "Ordered Items:")
            y -= 20
            
            # Table Data
            table_data = [["Item Name", "Qty", "Price(per unit)", "Subtotal (Rupees)"]]
            
            for item in current_cart.values():
                table_data.append([
                    item['name'],
                    str(item['quantity']),
                    str(float(str(item['price']).replace('₹', '').strip())),
                    str(item['subtotal'])
                ])
            
            # Create the table
            table = Table(table_data, colWidths=[200, 60, 80, 110])
            
            # Style the table
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            
            # Draw the table on PDF
            table.wrapOn(pdf, 60, y)
            table.drawOn(pdf, 60, y - (len(table_data) * 25))
            
            # Move down after table
            y -= (len(table_data) * 25) + 40
            
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(50, y, f"Final Bill : {grand_total}/-")
            
            y -= 40
            pdf.setFont("Helvetica", 10)
            pdf.drawString(50, y, "Thank you for ordering with Foodie Haven!")
            
            pdf.save()
            buffer.seek(0)
            

            return send_file(
                buffer,
                as_attachment=True,
                download_name="Order_Receipt.pdf",
                mimetype='application/pdf'
            )

        except Exception as e:
            db.session.rollback()
            print("Checkout Error:", e)
            flash(f"Error: {e}", "danger")

    return render_template('checkout.html',
                           cart=current_cart,
                           grand_total=grand_total,
                           order_summary=order_summary)
# ------------------------------------------------

# ------------------------------------------------


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # --- Add default admin if not present ---
        '''if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                email='admin@example.com',
                password=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("✅ Admin account created: username=admin, password=admin123")'''
        
        # --- Add some default food items for testing ---
        

    app.run(debug=True, port=5000)

    