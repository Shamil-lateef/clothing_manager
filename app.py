from flask import Flask, render_template, request, redirect, url_for, flash
from collections import defaultdict


app = Flask(__name__)

app.secret_key = "some-secret-key"  # needed for flash messages

# Simulated in-memory database
products = []


@app.route("/")
def index():
    return render_template("index.html", products=products)


@app.route("/add", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        image_url = request.form["image_url"]
        style_url = request.form["style_url"]
        total_cost = float(request.form["total_cost"])
        shipping_cost = float(request.form["shipping_cost"])

        # 🆕 Get multiple size-quantity fields from the form
        sizes = {}
        size_list = request.form.getlist("size[]")
        quantity_list = request.form.getlist("quantity[]")

        for s, q in zip(size_list, quantity_list):
            size = s.strip()
            qty = int(q.strip())
            if size:
                sizes[size] = qty

        total_units = sum(sizes.values())
        if total_units == 0:
            return "Error: total units must be greater than 0"

        unit_cost = round((total_cost + shipping_cost) / total_units, 2)
        selling_price = round(unit_cost * 1.5, 2)

        product = {
            "image_url": image_url,
            "style_url": style_url,
            "sizes": sizes,
            "unit_cost": unit_cost,
            "selling_price": selling_price,
        }

        products.append(product)
        return redirect(url_for("index"))

    return render_template("add_product.html")


@app.route("/sell", methods=["GET", "POST"])
def sell_product():
    if request.method == "POST":
        product_index = int(request.form["product_index"])
        size = request.form["size"]

        product = products[product_index]

        if size in product["sizes"] and product["sizes"][size] > 0:
            product["sizes"][size] -= 1
            flash(
                f"Sold 1 item of size {size} from product {product_index + 1}.",
                "success",
            )
        else:
            flash("This size is out of stock!", "danger")

        return redirect(url_for("sell_product"))

    return render_template("sell.html", products=products)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
