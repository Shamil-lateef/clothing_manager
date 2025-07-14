# Create a new file called migrate_revert.py in your project root
# Run this ONCE to add the revert functionality to your database

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

# Copy your app configuration here
app = Flask(__name__)

app.secret_key = "some-secret-key"

database_url = os.environ.get("DATABASE_URL")
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"sslmode": "require"}}
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///zuzi_store.db"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


def migrate_database():
    """Add revert functionality to existing database"""
    with app.app_context():
        try:
            # Add the is_reverted column to Sale table
            db.engine.execute(
                "ALTER TABLE sale ADD COLUMN is_reverted BOOLEAN DEFAULT 0"
            )
            print("is_reverted column to Sale table")
        except Exception as e:
            print(f"is_reverted column might already exist: {e}")

        try:
            # Create the SaleRevert table
            db.engine.execute(
                """
                CREATE TABLE sale_revert (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    size VARCHAR(50) NOT NULL,
                    quantity INTEGER NOT NULL,
                    selling_price FLOAT NOT NULL,
                    unit_cost FLOAT NOT NULL,
                    revert_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reverted_by INTEGER NOT NULL,
                    reason VARCHAR(500),
                    FOREIGN KEY (sale_id) REFERENCES sale(id),
                    FOREIGN KEY (product_id) REFERENCES product(id),
                    FOREIGN KEY (reverted_by) REFERENCES user(id)
                )
            """
            )
            print("Created SaleRevert table")
        except Exception as e:
            print(f"SaleRevert table might already exist: {e}")

        print("Database migration completed successfully!")


if __name__ == "__main__":
    migrate_database()
