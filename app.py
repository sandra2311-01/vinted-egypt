import os
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import Flask, render_template, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
client = MongoClient(os.getenv("MONGO_URI"))
db = client["vinted_egypt"]

try:
    client.admin.command("ping")
    print("MongoDB connected successfully!")
except Exception as e:
    print("MongoDB connection failed:")
    print(e)

@app.route("/")
def home():

    listings = db["listings"]

    all_listings = list(
        listings.find({"status": "available"})
    )

    return render_template(
        "home.html",
        listings=all_listings
    )

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        password_hash = generate_password_hash(password)

        users = db["users"]
        existing_user = users.find_one({"email": email})

        if existing_user:
            return "Email already registered"
        
        users.insert_one({
            "name": name,
            "email": email,
            "password_hash": password_hash
        })

        print("User saved successfully!")

    return render_template("register.html")
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        users = db["users"]

        user = users.find_one({"email": email})

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = str(user["_id"])
            session["user_name"] = user["name"]

            return "Login successful!"

        return "Invalid email or password"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    users = db["users"]

    user = users.find_one({
        "_id": ObjectId(session["user_id"])
    })

    return render_template("profile.html", user=user)

@app.route("/sell", methods=["GET", "POST"])
def sell():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        print("POST RECEIVED")

        title = request.form["title"]
        description = request.form["description"]
        price = request.form["price"]
        condition = request.form["condition"]
        city = request.form["city"]
        payment_methods = request.form.getlist("payment_methods")

        listings = db["listings"]

        listing = {
            "seller_id": session["user_id"],
            "title": title,
            "description": description,
            "price": int(price),
            "condition": condition,
            "city": city,
            "payment_methods": payment_methods,
            "status": "available"
        }

        print("ABOUT TO INSERT")

        result = listings.insert_one(listing)

        print("INSERT FINISHED")
        print("Listing ID:", result.inserted_id)
        print("Collection:", listings.name)
        print("Count:", listings.count_documents({}))

    return render_template("sell.html")