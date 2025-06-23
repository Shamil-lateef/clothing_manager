from flask import Flask, render_template, request, redirect, url_for
from collections import defaultdict

app = Flask(__name__)

# Simulated in-memory database
products = []


def parse_sizes(sizes_input):
    sizes = {}
    for item in sizes_input.split(","):
        if ":" in item:
            size, qty = item.strip().split(":")
            sizes[size.strip()] = int(qty.strip())
    return sizes


@app.route("/")
def index():
    return render_template("index.html", products=products)


@app.route("/add", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        image_url = request.form["image_url"]
        style_url = request.form["style_url"]
        sizes_input = request.form["sizes"]
        total_cost = float(request.form["total_cost"])
        shipping_cost = float(request.form["shipping_cost"])

        sizes = parse_sizes(sizes_input)
        total_units = sum(sizes.values())
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
