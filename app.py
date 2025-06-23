from flask import Flask, render_template, request, redirect, url_for, flash
from collections import defaultdict
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

app.secret_key = "some-secret-key"  # needed for flash messages

# SQLite database config
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"sslmode": "require"}}


db = SQLAlchemy(app)


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


# Create database tables
with app.app_context():
    db.create_all()


@app.route("/")
def index():
    low_stock_threshold = 3
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


@app.route("/add", methods=["GET", "POST"])
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

        unit_cost = round((total_cost + shipping_cost) / total_units, 2)
        selling_price = round(unit_cost * 1.5, 2)

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
def sell_product():
    if request.method == "POST":
        product_id = int(request.form["product_id"])
        size = request.form["size"]

        # Get size record
        size_entry = SizeQuantity.query.filter_by(
            product_id=product_id, size=size
        ).first()

        if size_entry and size_entry.quantity > 0:
            size_entry.quantity -= 1
            db.session.commit()
            flash(f"Sold 1 unit of size {size}.", "success")
        else:
            flash(f"Size '{size}' is out of stock!", "danger")

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
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == "POST":
        product.image_url = request.form["image_url"]
        product.style_url = request.form["style_url"]
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
            return redirect(url_for("edit_product", product_id=product_id))

        product.total_cost = total_cost
        product.shipping_cost = shipping_cost
        product.unit_cost = round((total_cost + shipping_cost) / total_units, 2)
        product.selling_price = round(product.unit_cost * 1.5, 2)

        # Remove old sizes
        SizeQuantity.query.filter_by(product_id=product_id).delete()

        # Add new sizes
        for size, qty in sizes.items():
            db.session.add(SizeQuantity(size=size, quantity=qty, product_id=product.id))

        db.session.commit()
        flash("Product updated successfully!", "success")
        return redirect(url_for("index"))

    # GET: pre-fill form with existing data
    sizes = product.sizes
    return render_template("edit_product.html", product=product, sizes=sizes)


@app.route("/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully!", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
