from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
import csv
from io import StringIO
from collections import defaultdict
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from functools import wraps


app = Flask(__name__)

app.secret_key = "some-secret-key"  # needed for flash messages

# Database configuration - works for both local development and production
database_url = os.environ.get("DATABASE_URL")
if database_url:
    # Production (Render) - PostgreSQL
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"sslmode": "require"}}
else:
    # Local development - SQLite
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///zuzi_store.db"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

# Optional: Disable SQLAlchemy modification tracking for better performance
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)

migrate = Migrate(app, db)


login_manager = LoginManager(app)
login_manager.login_view = "login"

bcrypt = Bcrypt(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Define models
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_url = db.Column(db.String(500))
    style_url = db.Column(db.String(500))
    total_cost = db.Column(db.Float)
    shipping_cost = db.Column(db.Float)
    unit_cost = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    sizes = db.relationship("SizeQuantity", backref="product", cascade="all, delete")


class SizeQuantity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    size = db.Column(db.String(50))
    quantity = db.Column(db.Integer)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    size = db.Column(db.String(50))
    quantity = db.Column(db.Integer)
    selling_price = db.Column(db.Float)
    unit_cost = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), default="employee")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == "admin"


# Initialize database tables
def init_db():
    """Initialize database tables"""
    try:
        db.create_all()
        print("Database tables created successfully!")

        # Create admin user if it doesn't exist
        admin_user = User.query.filter_by(username="admin").first()
        if not admin_user:
            hashed_pw = bcrypt.generate_password_hash("admin123").decode("utf-8")
            admin_user = User(username="admin", password_hash=hashed_pw, role="admin")
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created successfully!")
        else:
            print("Admin user already exists.")

    except Exception as e:
        print(f"Error initializing database: {e}")


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


# Routes
@app.route("/")
@login_required
def index():
    low_stock_threshold = 1
    products = Product.query.all()

    # Collect low stock items: list of dicts {product, size, quantity}
    low_stock_items = []
    for product in products:
        for sq in product.sizes:
            if sq.quantity <= low_stock_threshold:
                low_stock_items.append(
                    {"product": product, "size": sq.size, "quantity": sq.quantity}
                )

    return render_template(
        "index.html", products=products, low_stock_items=low_stock_items
    )


# 3. Update the create-admin route to set the admin role:
@app.route("/create-admin")
def create_admin():
    if User.query.filter_by(username="admin").first():
        return "Admin already exists."
    hashed_pw = bcrypt.generate_password_hash("admin123").decode("utf-8")
    user = User(username="admin", password_hash=hashed_pw, role="admin")
    db.session.add(user)
    db.session.commit()
    return "Admin user created. You can now log in at /login"


# 4. Add a route to create employee accounts (admin only):
@app.route("/create-employee", methods=["GET", "POST"])
@login_required
@admin_required
def create_employee():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "danger")
            return redirect(url_for("create_employee"))

        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        user = User(username=username, password_hash=hashed_pw, role="employee")
        db.session.add(user)
        db.session.commit()
        flash(f"Employee account '{username}' created successfully!", "success")
        return redirect(url_for("manage_users"))

    return render_template("create_employee.html")


# 5. Add a route to manage users (admin only):
@app.route("/manage-users")
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template("manage_users.html", users=users)


# 6. Add a route to delete users (admin only):
@app.route("/delete-user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == "admin" and User.query.filter_by(role="admin").count() == 1:
        flash("Cannot delete the last admin user!", "danger")
        return redirect(url_for("manage_users"))

    db.session.delete(user)
    db.session.commit()
    flash(f"User '{user.username}' deleted successfully!", "success")
    return redirect(url_for("manage_users"))


@app.route("/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_product():
    if request.method == "POST":
        image_url = request.form["image_url"]
        style_url = request.form["style_url"]
        total_cost = float(request.form["total_cost"])
        shipping_cost = float(request.form["shipping_cost"])

        size_list = request.form.getlist("size[]")
        quantity_list = request.form.getlist("quantity[]")

        sizes = {}
        for s, q in zip(size_list, quantity_list):
            sizes[s.strip()] = int(q.strip())

        total_units = sum(sizes.values())
        if total_units == 0:
            flash("Total quantity must be greater than 0.", "danger")
            return redirect(url_for("add_product"))
        total_cost = total_cost * 1400  # Convert to IQD
        shipping_cost = shipping_cost * 1400  # Convert to IQD

        unit_cost = (total_cost + shipping_cost) / total_units

        selling_price = int(
            round((unit_cost + 7000) / 1000) * 1000
        )  # Round to nearest 1000 IQD

        # Save product to DB
        product = Product(
            image_url=image_url,
            style_url=style_url,
            total_cost=total_cost,
            shipping_cost=shipping_cost,
            unit_cost=unit_cost,
            selling_price=selling_price,
        )
        db.session.add(product)
        db.session.flush()  # Assigns an ID

        for size, qty in sizes.items():
            db.session.add(SizeQuantity(size=size, quantity=qty, product_id=product.id))

        db.session.commit()
        flash("Product added successfully!", "success")
        return redirect(url_for("index"))

    return render_template("add_product.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell_product():
    if request.method == "POST":
        product_id = int(request.form["product_id"])
        size = request.form["size"]
        quantity = int(request.form["quantity"])

        # Get the product and size entry
        product = Product.query.get_or_404(product_id)
        size_entry = SizeQuantity.query.filter_by(
            product_id=product_id, size=size
        ).first()

        if size_entry and size_entry.quantity >= quantity:
            # Update inventory
            size_entry.quantity -= quantity

            # Record the sale
            sale = Sale(
                product_id=product_id,
                size=size,
                quantity=quantity,
                selling_price=product.selling_price,
                unit_cost=product.unit_cost,
            )
            db.session.add(sale)
            db.session.commit()

            flash(f"Sold {quantity} unit(s) of size {size}.", "success")
        else:
            flash(f"Not enough stock for size '{size}'!", "danger")

        return redirect(url_for("sell_product"))

    # Load all products and their sizes
    products = Product.query.all()
    return render_template("sell.html", products=products)


@app.route("/search", methods=["GET", "POST"])
def search_by_size():
    results = []
    size_query = ""

    if request.method == "POST":
        size_query = request.form["size"].strip()
        if size_query:
            results = (
                db.session.query(Product, SizeQuantity)
                .join(SizeQuantity)
                .filter(SizeQuantity.size == size_query, SizeQuantity.quantity > 0)
                .all()
            )

    return render_template("search.html", results=results, size_query=size_query)


@app.route("/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == "POST":
        product.image_url = request.form["image_url"]
        product.style_url = request.form["style_url"]

        # Get costs in USD (user input)
        total_cost_usd = float(request.form["total_cost"])
        shipping_cost_usd = float(request.form["shipping_cost"])

        size_list = request.form.getlist("size[]")
        quantity_list = request.form.getlist("quantity[]")

        sizes = {}
        for s, q in zip(size_list, quantity_list):
            sizes[s.strip()] = int(q.strip())

        total_units = sum(sizes.values())
        if total_units == 0:
            flash("Total quantity must be greater than 0.", "danger")
            return redirect(url_for("edit_product", product_id=product_id))

        # Convert USD to IQD (same as add_product)
        total_cost_iqd = total_cost_usd * 1400
        shipping_cost_iqd = shipping_cost_usd * 1400

        # Calculate unit cost and selling price in IQD
        unit_cost = (total_cost_iqd + shipping_cost_iqd) / total_units
        selling_price = (
            round((unit_cost + 7000) / 1000) * 1000
        )  # Round to nearest 1000 IQD

        # Update product with IQD values
        product.total_cost = total_cost_iqd
        product.shipping_cost = shipping_cost_iqd
        product.unit_cost = unit_cost
        product.selling_price = selling_price

        # Remove old sizes
        SizeQuantity.query.filter_by(product_id=product_id).delete()

        # Add new sizes
        for size, qty in sizes.items():
            db.session.add(SizeQuantity(size=size, quantity=qty, product_id=product.id))

        db.session.commit()
        flash("Product updated successfully!", "success")
        return redirect(url_for("index"))

    # GET: Convert IQD back to USD for form display
    total_cost_usd = product.total_cost / 1400 if product.total_cost else 0
    shipping_cost_usd = product.shipping_cost / 1400 if product.shipping_cost else 0

    sizes = product.sizes
    return render_template(
        "edit_product.html",
        product=product,
        sizes=sizes,
        total_cost_usd=total_cost_usd,
        shipping_cost_usd=shipping_cost_usd,
    )


@app.route("/delete/<int:product_id>", methods=["POST"])
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully!", "success")
    return redirect(url_for("index"))


@app.route("/export")
@login_required
@admin_required
def export_sales():
    sales = Sale.query.order_by(Sale.timestamp.desc()).all()

    # Create CSV in memory
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(
        [
            "Date",
            "Product ID",
            "Size",
            "Quantity",
            "Selling Price",
            "Unit Cost",
            "Profit",
        ]
    )

    for sale in sales:
        writer.writerow(
            [
                sale.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                sale.product_id,
                sale.size,
                sale.quantity,
                sale.selling_price,
                sale.unit_cost,
                round(sale.selling_price - sale.unit_cost, 2),
            ]
        )

    output = si.getvalue()
    si.close()

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=sales_report.csv"},
    )


@app.route("/report", methods=["GET", "POST"])
@login_required
@admin_required
def report():
    # Default to last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    if request.method == "POST":
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")

        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            # Add 23:59:59 to end_date to include the entire day
            end_date = end_date.replace(hour=23, minute=59, second=59)

    # 1. Sales Summary
    sales_summary = (
        db.session.query(
            func.count(Sale.id).label("total_sales"),
            func.sum(Sale.quantity).label("total_units_sold"),
            func.sum(Sale.selling_price * Sale.quantity).label("total_revenue"),
            func.sum(Sale.unit_cost * Sale.quantity).label("total_cost"),
            func.sum((Sale.selling_price - Sale.unit_cost) * Sale.quantity).label(
                "total_profit"
            ),
        )
        .filter(Sale.timestamp >= start_date, Sale.timestamp <= end_date)
        .first()
    )

    # 2. Product Performance
    product_performance = (
        db.session.query(
            Product.id,
            Product.image_url,
            Product.style_url,
            Product.selling_price,
            func.sum(Sale.quantity).label("units_sold"),
            func.sum(Sale.selling_price * Sale.quantity).label("revenue"),
            func.sum(Sale.unit_cost * Sale.quantity).label("cost"),
            func.sum((Sale.selling_price - Sale.unit_cost) * Sale.quantity).label(
                "profit"
            ),
        )
        .join(Sale)
        .filter(Sale.timestamp >= start_date, Sale.timestamp <= end_date)
        .group_by(Product.id)
        .order_by(desc("profit"))
        .all()
    )

    # 3. Size Performance
    size_performance = (
        db.session.query(
            Sale.size,
            func.count(Sale.id).label("sales_count"),
            func.sum(Sale.quantity).label("total_quantity"),
            func.sum(Sale.selling_price * Sale.quantity).label("total_revenue"),
        )
        .filter(Sale.timestamp >= start_date, Sale.timestamp <= end_date)
        .group_by(Sale.size)
        .order_by(desc("total_quantity"))
        .all()
    )

    # 4. Daily Sales Trend
    daily_sales = (
        db.session.query(
            func.date(Sale.timestamp).label("sale_date"),
            func.count(Sale.id).label("sales_count"),
            func.sum(Sale.quantity).label("units_sold"),
            func.sum(Sale.selling_price * Sale.quantity).label("revenue"),
            func.sum((Sale.selling_price - Sale.unit_cost) * Sale.quantity).label(
                "profit"
            ),
        )
        .filter(Sale.timestamp >= start_date, Sale.timestamp <= end_date)
        .group_by(func.date(Sale.timestamp))
        .order_by("sale_date")
        .all()
    )

    # 5. Low Stock Items
    low_stock_items = (
        db.session.query(Product, SizeQuantity)
        .join(SizeQuantity)
        .filter(SizeQuantity.quantity <= 2)
        .order_by(SizeQuantity.quantity)
        .all()
    )

    # 6. Top Performing Products (by profit)
    top_products = product_performance[:5] if product_performance else []

    # 7. Worst Performing Products (by profit)
    worst_products = product_performance[-5:] if len(product_performance) >= 5 else []

    # 8. Current Inventory Value
    inventory_value = (
        db.session.query(
            func.sum(Product.unit_cost * SizeQuantity.quantity).label(
                "total_inventory_cost"
            ),
            func.sum(Product.selling_price * SizeQuantity.quantity).label(
                "total_inventory_value"
            ),
            func.sum(SizeQuantity.quantity).label("total_units_in_stock"),
        )
        .join(SizeQuantity)
        .first()
    )

    return render_template(
        "report.html",
        start_date=start_date,
        end_date=end_date,
        sales_summary=sales_summary,
        product_performance=product_performance,
        size_performance=size_performance,
        daily_sales=daily_sales,
        low_stock_items=low_stock_items,
        top_products=top_products,
        worst_products=worst_products,
        inventory_value=inventory_value,
    )


@app.route("/export_detailed_report")
@login_required
@admin_required
def export_detailed_report():
    # Get date range from query parameters
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        end_date = end_date.replace(hour=23, minute=59, second=59)
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

    # Get all sales data
    sales_data = (
        db.session.query(
            Sale.timestamp,
            Product.id.label("product_id"),
            Sale.size,
            Sale.quantity,
            Sale.selling_price,
            Sale.unit_cost,
            ((Sale.selling_price - Sale.unit_cost) * Sale.quantity).label("profit"),
        )
        .join(Product)
        .filter(Sale.timestamp >= start_date, Sale.timestamp <= end_date)
        .order_by(Sale.timestamp.desc())
        .all()
    )

    # Create CSV
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(
        [
            "Date",
            "Product ID",
            "Size",
            "Quantity",
            "Selling Price",
            "Unit Cost",
            "Total Revenue",
            "Total Cost",
            "Profit",
        ]
    )

    for sale in sales_data:
        total_revenue = sale.selling_price * sale.quantity
        total_cost = sale.unit_cost * sale.quantity
        writer.writerow(
            [
                sale.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                sale.product_id,
                sale.size,
                sale.quantity,
                f"{sale.selling_price:.0f}",
                f"{sale.unit_cost:.0f}",
                f"{total_revenue:.0f}",
                f"{total_cost:.0f}",
                f"{sale.profit:.0f}",
            ]
        )

    output = si.getvalue()
    si.close()

    filename = f"detailed_report_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and user.check_password(request.form["password"]):
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.before_first_request
def initialize_db():
    with app.app_context():
        db.create_all()  # Recreate all tables
        print("Database tables initialized!")


if __name__ == "__main__":
    # Initialize database when app starts
    with app.app_context():
        init_db()

    app.run(host="0.0.0.0", port=10000)
