import os
import uuid
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    url_for,
    abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId


# --------------------------------------------------
# APP SETUP
# --------------------------------------------------

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

client = MongoClient(os.getenv("MONGO_URI"))
db = client["vinted_egypt"]
# --------------------------------------------------
# DATABASE INDEXES
# --------------------------------------------------

db["conversations"].create_index(
    [
        ("listing_id", ASCENDING),
        ("buyer_id", ASCENDING),
        ("seller_id", ASCENDING)
    ],
    unique=True
)

db["messages"].create_index(
    [
        ("conversation_id", ASCENDING),
        ("created_at", ASCENDING)
    ]
)

# --------------------------------------------------
# MONGODB CONNECTION TEST
# --------------------------------------------------

try:
    client.admin.command("ping")
    print("MongoDB connected successfully!")

except Exception as e:
    print("MongoDB connection failed:")
    print(e)


# --------------------------------------------------
# IMAGE SETTINGS
# --------------------------------------------------

UPLOAD_FOLDER = os.path.join("static", "uploads")

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

MAX_IMAGES = 5

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Maximum total request size = 20 MB
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def save_image(image):

    filename = secure_filename(image.filename)

    unique_filename = (
        f"{uuid.uuid4().hex}_{filename}"
    )

    image.save(
        os.path.join(
            app.config["UPLOAD_FOLDER"],
            unique_filename
        )
    )

    return unique_filename


def get_owned_listing(listing_id):

    if not ObjectId.is_valid(listing_id):
        abort(404)

    listing = db["listings"].find_one({
        "_id": ObjectId(listing_id)
    })

    if not listing:
        abort(404)

    if listing["seller_id"] != session.get("user_id"):
        abort(403)

    return listing
def get_user_conversation(conversation_id):

    if not ObjectId.is_valid(conversation_id):
        abort(404)

    conversation = db["conversations"].find_one({
        "_id": ObjectId(conversation_id)
    })

    if not conversation:
        abort(404)

    current_user_id = session.get("user_id")

    if current_user_id not in [
        conversation["buyer_id"],
        conversation["seller_id"]
    ]:
        abort(403)

    return conversation

# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def home():

    listings = db["listings"]

    all_listings = list(
        listings.find({
            "status": "available"
        })
    )

    return render_template(
        "home.html",
        listings=all_listings
    )


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or not password:
            return "Please fill in all fields", 400

        users = db["users"]

        existing_user = users.find_one({
            "email": email
        })

        if existing_user:
            return "Email already registered", 400

        password_hash = generate_password_hash(
            password
        )

        users.insert_one({
            "name": name,
            "email": email,
            "password_hash": password_hash
        })

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = (
            request.form["email"]
            .strip()
            .lower()
        )

        password = request.form["password"]

        users = db["users"]

        user = users.find_one({
            "email": email
        })

        if (
            user
            and check_password_hash(
                user["password_hash"],
                password
            )
        ):

            session["user_id"] = str(
                user["_id"]
            )

            session["user_name"] = user["name"]

            return redirect(
                url_for("home")
            )

        return "Invalid email or password", 401

    return render_template(
        "login.html"
    )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# --------------------------------------------------
# OWN PROFILE
# --------------------------------------------------

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    users = db["users"]

    user = users.find_one({
        "_id": ObjectId(
            session["user_id"]
        )
    })

    return render_template(
        "profile.html",
        user=user
    )


# --------------------------------------------------
# CREATE LISTING
# --------------------------------------------------

@app.route(
    "/sell",
    methods=["GET", "POST"]
)
def sell():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        # ------------------------------
        # NORMAL FORM DATA
        # ------------------------------

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        price = request.form.get(
            "price",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        condition = request.form.get(
            "condition",
            ""
        ).strip()

        city = request.form.get(
            "city",
            ""
        ).strip()

        payment_methods = (
            request.form.getlist(
                "payment_methods"
            )
        )

        # ------------------------------
        # BASIC VALIDATION
        # ------------------------------

        if (
            not title
            or not description
            or not category
            or not condition
            or not city
        ):
            return (
                "Please fill in all required fields",
                400
            )

        try:
            price = int(price)

            if price <= 0:
                raise ValueError

        except ValueError:
            return (
                "Price must be a positive whole number",
                400
            )

        if not payment_methods:
            return (
                "Please select at least one payment method",
                400
            )

        # ------------------------------
        # IMAGES
        # ------------------------------

        images = request.files.getlist(
            "images"
        )

        images = [
            image
            for image in images
            if image.filename != ""
        ]

        if not images:
            return (
                "Please upload at least one image",
                400
            )

        if len(images) > MAX_IMAGES:
            return (
                "You can upload a maximum of 5 images",
                400
            )

        # Validate BEFORE saving
        for image in images:

            if not allowed_file(
                image.filename
            ):
                return (
                    "Only JPG, JPEG, PNG and WEBP images are allowed",
                    400
                )

        saved_images = []

        for image in images:

            saved_filename = save_image(
                image
            )

            saved_images.append(
                saved_filename
            )

        # ------------------------------
        # SAVE LISTING
        # ------------------------------

        listings = db["listings"]

        listing = {

            "seller_id":
                session["user_id"],

            "title":
                title,

            "description":
                description,

            "price":
                price,

            "category":
                category,

            "condition":
                condition,

            "city":
                city,

            "payment_methods":
                payment_methods,

            "images":
                saved_images,

            "status":
                "available"
        }

        listings.insert_one(
            listing
        )

        return redirect(
            url_for("home")
        )

    return render_template(
        "sell.html"
    )


# --------------------------------------------------
# LISTING DETAILS
# --------------------------------------------------

@app.route(
    "/listing/<listing_id>"
)
def listing_details(listing_id):

    if not ObjectId.is_valid(
        listing_id
    ):
        abort(404)

    listings = db["listings"]
    users = db["users"]

    listing = listings.find_one({
        "_id": ObjectId(
            listing_id
        )
    })

    if not listing:
        abort(404)

    # Hidden listings can only be viewed by their owner
    if (
        listing.get("status") == "hidden"
        and session.get("user_id") != listing.get("seller_id")
    ):
        abort(404)

    seller = None

    seller_id = listing.get(
        "seller_id"
    )

    if (
        seller_id
        and ObjectId.is_valid(
            seller_id
        )
    ):
        seller = users.find_one({
            "_id": ObjectId(
                seller_id
            )
        })

    # Check whether this listing is already
    # in the current user's favorites
    is_favorite = False

    if (
        session.get("user_id")
        and session.get("user_id") != listing.get("seller_id")
    ):

        favorite = db["favorites"].find_one({
            "user_id": session["user_id"],
            "listing_id": listing["_id"]
        })

        is_favorite = favorite is not None


    return render_template(
        "listing_details.html",
        listing=listing,
        seller=seller,
        is_favorite=is_favorite
    )


# --------------------------------------------------
# EDIT LISTING
# --------------------------------------------------

@app.route(
    "/listing/<listing_id>/edit",
    methods=["GET", "POST"]
)
def edit_listing(listing_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    listing = get_owned_listing(
        listing_id
    )

    # Sold listings are locked from further editing
    if listing.get("status") == "sold":
        return (
            "Sold listings cannot be edited",
            400
        )

    if request.method == "POST":

        # ------------------------------
        # FORM DATA
        # ------------------------------

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        price = request.form.get(
            "price",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        condition = request.form.get(
            "condition",
            ""
        ).strip()

        city = request.form.get(
            "city",
            ""
        ).strip()

        payment_methods = (
            request.form.getlist(
                "payment_methods"
            )
        )

        remove_images = (
            request.form.getlist(
                "remove_images"
            )
        )

        new_images = (
            request.files.getlist(
                "new_images"
            )
        )

        # ------------------------------
        # NORMAL FIELD VALIDATION
        # ------------------------------

        if (
            not title
            or not description
            or not category
            or not condition
            or not city
        ):
            return (
                "Please fill in all required fields",
                400
            )

        # ------------------------------
        # PRICE VALIDATION
        # ------------------------------

        try:

            price = int(price)

            if price <= 0:
                raise ValueError

        except ValueError:

            return (
                "Price must be a positive whole number",
                400
            )

        # ------------------------------
        # CATEGORY VALIDATION
        # ------------------------------

        allowed_categories = [
            "Fashion",
            "Electronics",
            "Home",
            "Books",
            "Sports",
            "Other"
        ]

        if category not in allowed_categories:

            return (
                "Invalid category",
                400
            )

        # ------------------------------
        # PAYMENT METHOD VALIDATION
        # ------------------------------

        allowed_payment_methods = [
            "Cash",
            "InstaPay"
        ]

        if not payment_methods:

            return (
                "Please select at least one payment method",
                400
            )

        if any(
            method not in allowed_payment_methods
            for method in payment_methods
        ):

            return (
                "Invalid payment method",
                400
            )

        # ------------------------------
        # CURRENT IMAGES
        # ------------------------------

        current_images = listing.get(
            "images",
            []
        )

        # Support older single-image listings
        if (
            not current_images
            and listing.get("image")
        ):

            current_images = [
                listing["image"]
            ]

        # Only allow images belonging to
        # this listing to be removed
        remove_images = [
            image
            for image in remove_images
            if image in current_images
        ]

        updated_images = [
            image
            for image in current_images
            if image not in remove_images
        ]

        # ------------------------------
        # NEW IMAGES
        # ------------------------------

        valid_new_images = [
            image
            for image in new_images
            if image.filename != ""
        ]

        total_images = (
            len(updated_images)
            + len(valid_new_images)
        )

        if total_images > MAX_IMAGES:

            return (
                "You can have a maximum of 5 images",
                400
            )

        if total_images == 0:

            return (
                "A listing must have at least one image",
                400
            )

        # Validate every image before
        # saving any of them
        for image in valid_new_images:

            if not allowed_file(
                image.filename
            ):

                return (
                    "Only JPG, JPEG, PNG and WEBP images are allowed",
                    400
                )

        # ------------------------------
        # SAVE NEW IMAGES
        # ------------------------------

        for image in valid_new_images:

            saved_filename = save_image(
                image
            )

            updated_images.append(
                saved_filename
            )

        # ------------------------------
        # UPDATE MONGODB
        # ------------------------------

        db["listings"].update_one(

            {
                "_id": listing["_id"]
            },

            {
                "$set": {

                    "title":
                        title,

                    "description":
                        description,

                    "price":
                        price,

                    "category":
                        category,

                    "condition":
                        condition,

                    "city":
                        city,

                    "payment_methods":
                        payment_methods,

                    "images":
                        updated_images
                },

                # Remove old single-image
                # field if it still exists
                "$unset": {
                    "image": ""
                }
            }
        )

        # ------------------------------
        # DELETE REMOVED IMAGE FILES
        # ------------------------------

        for image in remove_images:

            image_path = os.path.join(
                app.config[
                    "UPLOAD_FOLDER"
                ],
                image
            )

            if os.path.exists(
                image_path
            ):

                os.remove(
                    image_path
                )

        # ------------------------------
        # REDIRECT
        # ------------------------------

        return redirect(
            url_for(
                "listing_details",
                listing_id=listing_id
            )
        )

    return render_template(
        "edit_listing.html",
        listing=listing
    )


# --------------------------------------------------
# DELETE LISTING
# --------------------------------------------------

@app.route("/listing/<listing_id>/delete", methods=["POST"])
def delete_listing(listing_id):

    # ------------------------------
    # LOGIN CHECK
    # ------------------------------

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    # ------------------------------
    # GET LISTING + OWNERSHIP CHECK
    # ------------------------------

    listing = get_owned_listing(
        listing_id
    )

    # ------------------------------
    # GET LISTING IMAGES
    # ------------------------------

    images = listing.get(
        "images",
        []
    )

    # Support older listings that
    # used a single "image" field
    if (
        not images
        and listing.get("image")
    ):
        images = [
            listing["image"]
        ]

    # ------------------------------
    # DELETE LISTING FROM MONGODB
    # ------------------------------

    db["listings"].delete_one(
        {
            "_id": listing["_id"]
        }
    )

    # ------------------------------
    # DELETE IMAGE FILES
    # ------------------------------

    for image in images:

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            image
        )

        if os.path.exists(
            image_path
        ):
            os.remove(
                image_path
            )

    # ------------------------------
    # REDIRECT
    # ------------------------------

    return redirect(
        url_for("home")
    )


# --------------------------------------------------
# HIDE LISTING
# --------------------------------------------------

@app.route("/listing/<listing_id>/hide", methods=["POST"])
def hide_listing(listing_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    listing = get_owned_listing(
        listing_id
    )

    # Only available listings can be hidden
    if listing.get("status", "available") != "available":
        return (
            "Only available listings can be hidden",
            400
        )

    db["listings"].update_one(
        {
            "_id": listing["_id"]
        },
        {
            "$set": {
                "status": "hidden"
            }
        }
    )

    return redirect(
        url_for(
            "listing_details",
            listing_id=listing_id
        )
    )


# --------------------------------------------------
# UNHIDE LISTING
# --------------------------------------------------

@app.route("/listing/<listing_id>/unhide", methods=["POST"])
def unhide_listing(listing_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    listing = get_owned_listing(
        listing_id
    )

    # Only hidden listings can be unhidden
    if listing.get("status") != "hidden":
        return (
            "Only hidden listings can be unhidden",
            400
        )

    db["listings"].update_one(
        {
            "_id": listing["_id"]
        },
        {
            "$set": {
                "status": "available"
            }
        }
    )

    return redirect(
        url_for(
            "listing_details",
            listing_id=listing_id
        )
    )


# --------------------------------------------------
# MARK LISTING AS SOLD
# --------------------------------------------------

@app.route("/listing/<listing_id>/mark-sold", methods=["POST"])
def mark_listing_sold(listing_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    listing = get_owned_listing(
        listing_id
    )

    # Available and reserved listings can be marked sold
    if listing.get("status", "available") not in [
        "available",
        "reserved"
    ]:
        return (
            "Only available or reserved listings can be marked as sold",
            400
        )

    db["listings"].update_one(
        {
            "_id": listing["_id"]
        },
        {
            "$set": {
                "status": "sold"
            },
            "$unset": {
                "reserved_for": ""
            }
        }
    )

    return redirect(
        url_for(
            "listing_details",
            listing_id=listing_id
        )
    )
# --------------------------------------------------
# MY LISTINGS
# --------------------------------------------------

@app.route("/my-listings")
def my_listings():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    all_my_listings = list(
        db["listings"].find({
            "seller_id": session["user_id"]
        })
    )

    return render_template(
        "my_listings.html",
        listings=all_my_listings
    )
# --------------------------------------------------
# START CONVERSATION
# --------------------------------------------------

@app.route(
    "/listing/<listing_id>/contact",
    methods=["POST"]
)
def start_conversation(listing_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    if not ObjectId.is_valid(listing_id):
        abort(404)

    listing = db["listings"].find_one({
        "_id": ObjectId(listing_id)
    })

    if not listing:
        abort(404)

    # Buyers cannot start conversations
    # about hidden or sold listings
    if listing.get("status", "available") != "available":
        return (
            "This listing is not currently available",
            400
        )

    seller_id = listing["seller_id"]
    buyer_id = session["user_id"]

    # Seller cannot message themselves
    if seller_id == buyer_id:
        return (
            "You cannot contact yourself about your own listing",
            400
        )

    conversations = db["conversations"]

    existing_conversation = conversations.find_one({
        "listing_id": listing["_id"],
        "buyer_id": buyer_id,
        "seller_id": seller_id
    })

    if existing_conversation:

        return redirect(
            url_for(
                "conversation",
                conversation_id=existing_conversation["_id"]
            )
        )

    now = datetime.now(timezone.utc)

    try:

        result = conversations.insert_one({
            "listing_id": listing["_id"],
            "buyer_id": buyer_id,
            "seller_id": seller_id,
            "created_at": now,
            "updated_at": now
        })

        conversation_id = result.inserted_id

    except DuplicateKeyError:

        existing_conversation = conversations.find_one({
            "listing_id": listing["_id"],
            "buyer_id": buyer_id,
            "seller_id": seller_id
        })

        conversation_id = existing_conversation["_id"]

    return redirect(
        url_for(
            "conversation",
            conversation_id=conversation_id
        )
    )


# --------------------------------------------------
# CONVERSATION
# --------------------------------------------------

@app.route(
    "/messages/<conversation_id>",
    methods=["GET", "POST"]
)
def conversation(conversation_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    conversation = get_user_conversation(
        conversation_id
    )

    if request.method == "POST":

        body = request.form.get(
            "message",
            ""
        ).strip()

        if not body:
            return (
                "Message cannot be empty",
                400
            )

        if len(body) > 1000:
            return (
                "Message cannot exceed 1000 characters",
                400
            )

        now = datetime.now(timezone.utc)

        db["messages"].insert_one({
            "conversation_id": conversation["_id"],
            "sender_id": session["user_id"],
            "body": body,
            "created_at": now
        })

        db["conversations"].update_one(
            {
                "_id": conversation["_id"]
            },
            {
                "$set": {
                    "updated_at": now
                }
            }
        )

        return redirect(
            url_for(
                "conversation",
                conversation_id=conversation_id
            )
        )

    listing = db["listings"].find_one({
        "_id": conversation["listing_id"]
    })

    messages = list(
        db["messages"]
        .find({
            "conversation_id": conversation["_id"]
        })
        .sort(
            "created_at",
            ASCENDING
        )
    )

    buyer = db["users"].find_one({
        "_id": ObjectId(
            conversation["buyer_id"]
        )
    })

    seller = db["users"].find_one({
        "_id": ObjectId(
            conversation["seller_id"]
        )
    })

    reserved_for_this_buyer = (
        listing
        and listing.get("status") == "reserved"
        and str(listing.get("reserved_for"))
        == str(conversation["buyer_id"])
    )

    return render_template(
        "conversation.html",
        conversation=conversation,
        listing=listing,
        messages=messages,
        buyer=buyer,
        seller=seller,
        reserved_for_this_buyer=reserved_for_this_buyer
    )


# --------------------------------------------------
# MESSAGE INBOX
# --------------------------------------------------

@app.route("/messages")
def messages_inbox():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    current_user_id = session["user_id"]

    conversations = list(
        db["conversations"]
        .find({
            "$or": [
                {
                    "buyer_id":
                        current_user_id
                },
                {
                    "seller_id":
                        current_user_id
                }
            ]
        })
        .sort(
            "updated_at",
            -1
        )
    )

    conversation_cards = []

    for conversation_item in conversations:

        listing = db["listings"].find_one({
            "_id":
                conversation_item["listing_id"]
        })

        if (
            conversation_item["buyer_id"]
            == current_user_id
        ):

            other_user_id = (
                conversation_item[
                    "seller_id"
                ]
            )

        else:

            other_user_id = (
                conversation_item[
                    "buyer_id"
                ]
            )

        other_user = db["users"].find_one({
            "_id": ObjectId(
                other_user_id
            )
        })

        last_message = (
            db["messages"].find_one(
                {
                    "conversation_id":
                        conversation_item["_id"]
                },
                sort=[
                    (
                        "created_at",
                        -1
                    )
                ]
            )
        )

        conversation_cards.append({
            "conversation":
                conversation_item,

            "listing":
                listing,

            "other_user":
                other_user,

            "last_message":
                last_message
        })

    return render_template(
        "messages.html",
        conversations=conversation_cards
    )
# --------------------------------------------------
# RESERVE LISTING FOR BUYER
# --------------------------------------------------

@app.route(
    "/messages/<conversation_id>/reserve",
    methods=["POST"]
)
def reserve_listing(conversation_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    conversation = get_user_conversation(
        conversation_id
    )

    # Only the seller can reserve the item
    if session["user_id"] != conversation["seller_id"]:
        abort(403)

    listing = db["listings"].find_one({
        "_id": conversation["listing_id"]
    })

    if not listing:
        abort(404)

    # Only available listings can be reserved
    if listing.get("status", "available") != "available":
        return (
            "Only available listings can be reserved",
            400
        )

    db["listings"].update_one(
        {
            "_id": listing["_id"]
        },
        {
            "$set": {
                "status": "reserved",
                "reserved_for": conversation["buyer_id"]
            }
        }
    )

    return redirect(
        url_for(
            "conversation",
            conversation_id=conversation_id
        )
    )


# --------------------------------------------------
# CANCEL RESERVATION
# --------------------------------------------------

@app.route(
    "/messages/<conversation_id>/cancel-reservation",
    methods=["POST"]
)
def cancel_reservation(conversation_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    conversation = get_user_conversation(
        conversation_id
    )

    # Only the seller can cancel
    if session["user_id"] != conversation["seller_id"]:
        abort(403)

    listing = db["listings"].find_one({
        "_id": conversation["listing_id"]
    })

    if not listing:
        abort(404)

    if listing.get("status") != "reserved":
        return (
            "This listing is not reserved",
            400
        )

    # Make sure this reservation belongs
    # to the buyer in this conversation
    if (
        str(listing.get("reserved_for"))
        != str(conversation["buyer_id"])
    ):
        abort(403)

    db["listings"].update_one(
        {
            "_id": listing["_id"]
        },
        {
            "$set": {
                "status": "available"
            },
            "$unset": {
                "reserved_for": ""
            }
        }
    )

    return redirect(
        url_for(
            "conversation",
            conversation_id=conversation_id
        )
    )
# --------------------------------------------------
# ADD FAVORITE
# --------------------------------------------------

@app.route(
    "/listing/<listing_id>/favorite",
    methods=["POST"]
)
def add_favorite(listing_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    if not ObjectId.is_valid(listing_id):
        abort(404)

    listing = db["listings"].find_one({
        "_id": ObjectId(listing_id)
    })

    if not listing:
        abort(404)

    if listing.get("status", "available") != "available":
        return (
            "Only available listings can be favorited",
            400
        )

    if listing["seller_id"] == session["user_id"]:
        return (
            "You cannot favorite your own listing",
            400
        )

    db["favorites"].update_one(
        {
            "user_id": session["user_id"],
            "listing_id": listing["_id"]
        },
        {
            "$setOnInsert": {
                "user_id": session["user_id"],
                "listing_id": listing["_id"],
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    return redirect(
        url_for(
            "listing_details",
            listing_id=listing_id
        )
    )


# --------------------------------------------------
# REMOVE FAVORITE
# --------------------------------------------------

@app.route(
    "/listing/<listing_id>/unfavorite",
    methods=["POST"]
)
def remove_favorite(listing_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    if not ObjectId.is_valid(listing_id):
        abort(404)

    db["favorites"].delete_one({
        "user_id": session["user_id"],
        "listing_id": ObjectId(listing_id)
    })

    return redirect(
        url_for(
            "listing_details",
            listing_id=listing_id
        )
    )


# --------------------------------------------------
# MY FAVORITES
# --------------------------------------------------

@app.route("/favorites")
def favorites():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    favorite_records = list(
        db["favorites"].find({
            "user_id": session["user_id"]
        })
    )

    favorite_listings = []

    for favorite in favorite_records:

        listing = db["listings"].find_one({
            "_id": favorite["listing_id"]
        })

        if (
            listing
            and listing.get("status", "available") == "available"
        ):
            favorite_listings.append(
                listing
            )

    return render_template(
        "favorites.html",
        listings=favorite_listings
    )
# --------------------------------------------------
# RUN APP
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)