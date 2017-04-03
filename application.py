from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import gettempdir

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = gettempdir()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    
    # store the user's current cash
    cash = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])[0]["cash"]
    
    # store the all of the user's stock information
    stocks_shares = db.execute("SELECT * FROM inventory WHERE user_id = :user_id", user_id=session["user_id"])
    
    stock_list = []
    stock_totals = []
    
    # for each stock, add its information into a new dictionary to be sent to the html file, and add it to the list
    for stock in stocks_shares:
        current_stock_info = {'symbol': stock["symbol"], 'name': lookup(stock["symbol"])["name"], 'shares': stock["shares"], 
                'price': usd(stock["price"]), 'total': usd(stock["total"])}
        stock_list.append(current_stock_info)
        stock_totals.append(lookup(stock["symbol"])["price"] * float(stock["shares"]))
    
    # calculate the total cash (the sum of all the stock totals)
    total_inventory_cash = sum(stock_totals) + cash
    
    # show the index template
    return render_template("index.html", stock_list=stock_list, total_inventory_cash=usd(total_inventory_cash), cash=usd(cash))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    
    # if the purchase is submitted
    if request.method == "POST":
        
        # ensure that the user enters a valid symbol
        if not request.form.get("symbol"):
            return apology("must provide a stock symbol")
        
        # ensure that the symbol entered exists    
        if not lookup(request.form.get("symbol")):
            return apology("stock symbol doesn't exist")
            
        # ensure that the user enters a number of shares
        if not request.form.get("shares"):
            return apology("must provide a valid number of shares")
        
        # ensure that the number of shares entered is more than 0
        if int(request.form.get("shares")) < 1:
            return apology("must enter a positive number of shares")
        
        # store the current cash value of the user
        cash = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])[0]["cash"]
        
        # store the total price of the shares the user is purchasing
        total_price = int(request.form.get("shares")) * lookup(request.form.get("symbol"))["price"]
        
        # ensure that the user can afford the shares
        if total_price > float(cash):
            return apology("Come back when you have more money")
        
        # store the user's rows that contain the desired stock
        user_stocks = db.execute("SELECT * FROM inventory WHERE user_id = :user_id AND symbol = :symbol", 
                                    user_id=session["user_id"], symbol=request.form.get("symbol").upper())
        
        # if the user has not bought this stock yet, add it to the inventory
        if len(user_stocks) == 0:
            db.execute("INSERT INTO inventory (user_id, symbol, shares, price, total) VALUES(:user_id, :symbol, :shares, :price, :total)", 
                            user_id=session["user_id"], symbol=request.form.get("symbol").upper(), shares=request.form.get("shares"), 
                            price=lookup(request.form.get("symbol"))["price"], total=int(request.form.get("shares")) * lookup(request.form.get("symbol"))["price"])
        
        # if the user has bought this stock already, update in the invetory
        if len(user_stocks) > 0:
            # store the number of shares of the stock that the user currently has
            shares_held = db.execute("SELECT * FROM inventory WHERE user_id = :user_id AND symbol = :symbol", 
                                    user_id=session["user_id"], symbol=request.form.get("symbol").upper())[0]["shares"]
            db.execute("UPDATE inventory SET shares = :shares, price = :price, total = :total WHERE user_id = :user_id AND symbol = :symbol", 
                            shares=int(request.form.get("shares")) + shares_held, user_id=session["user_id"], price=lookup(request.form.get("symbol"))["price"], symbol=request.form.get("symbol").upper(), total=(int(request.form.get("shares")) + shares_held) * lookup(request.form.get("symbol"))["price"])
        
        # insert the transaction into the transactions database
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)", 
                        symbol=request.form.get("symbol").upper(), user_id=session["user_id"], shares=request.form.get("shares"), price=usd(lookup(request.form.get("symbol"))["price"]))
        
        
        # update the user's cash after the purchase
        db.execute("UPDATE users SET cash = :cash", cash=cash - total_price)
    
        # redirect to the home page
        return redirect(url_for("index"))
    
    # if the "buy" button in the toolbar is clicked, show the buy page
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    
    # store all the individual transactions made by the user
    user_history = db.execute("SELECT * FROM transactions WHERE user_id = :user_id", user_id=session["user_id"])
    
    # show the history template
    return render_template("history.html", user_history=user_history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""
    
    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    
    # if the "quote" is submitted
    if request.method == "POST":
        
        # ensure that the user enters a symbol
        if not request.form.get("symbol"):
            return apology("must provide a stock symbol")
        
        # ensure that the symbol entered is valid
        if not lookup(request.form.get("symbol")):
            return apology("symbol doesn't exist")
        
        # store the symbol's returned dictionary from lookup
        symbol_dict = lookup(request.form.get("symbol"))
        
        # print out a statement with the stock name, price and symbol
        return render_template("quoted.html", name=symbol_dict['name'], price=symbol_dict['price'], symbol=symbol_dict['symbol'])
        
    # if the quote function in the toolbar is called, show the quote page
    else:
        return render_template("quote.html")
    

@app.route("/register", methods=["GET", "POST"])
def register():
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was created
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was created
        elif not request.form.get("password"):
            return apology("must provide password")
            
        # ensure that confirmed password was entered
        elif not request.form.get("confirm_password"):
            return apology("must re-type password")
        
        # ensure that the username is unique
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(rows) > 0:
            return apology("username already exists")
        
        # ensure that both passwords are the same
        password1 = request.form.get("password")
        password2 = request.form.get("confirm_password")
        if password1 != password2:
            return apology("passwords must match")
        
        # insert the new account into the database
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get("username"),
                    hash=pwd_context.encrypt(request.form.get("password")))
        
        # upon finishing registration, go to login page
        return render_template("login.html")
    
    # if register button is clicked in the toolbar, show the register page
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    
    # if the purchase is submitted
    if request.method == "POST":
        
        # ensure that the user enters a valid symbol
        if not request.form.get("symbol"):
            return apology("must provide a stock symbol")
        
        # ensure that the symbol entered exists    
        if not lookup(request.form.get("symbol")):
            return apology("stock symbol doesn't exist")
            
        # ensure that the user enters a number of shares
        if not request.form.get("shares"):
            return apology("must provide a valid number of shares")
        
        # ensure that the number of shares entered is more than 0
        if int(request.form.get("shares")) < 1:
            return apology("must enter a positive number of shares")
        
        # store the current cash value of the user
        cash = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])[0]["cash"]
        
        # store the total price of the shares the user is purchasing
        total_price = int(request.form.get("shares")) * lookup(request.form.get("symbol"))["price"]
        
        # store the number of shares of the stock that the user currently has
        shares_held = db.execute("SELECT * FROM inventory WHERE user_id = :user_id AND symbol = :symbol", 
                                    user_id=session["user_id"], symbol=request.form.get("symbol").upper())[0]["shares"]
        
        # ensure that the user can afford the shares
        if int(request.form.get("shares")) > shares_held:
            return apology("You don't have that many shares")
        
        # store the user's rows that contain the desired stock
        user_stocks = db.execute("SELECT * FROM inventory WHERE user_id = :user_id AND symbol = :symbol", 
                                    user_id=session["user_id"], symbol=request.form.get("symbol"))
        
        # update the number of shares in the invetory
        db.execute("UPDATE inventory SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol", 
                            shares=shares_held - int(request.form.get("shares")), user_id=session["user_id"], symbol=request.form.get("symbol").upper())
        
        # delete the row if the resulting number of shares is 0
        if shares_held - int(request.form.get("shares")) == 0:
            db.execute("DELETE FROM inventory WHERE user_id = :user_id AND symbol = :symbol", user_id=session["user_id"], symbol=request.form.get("symbol").upper())
        
        # update the user's cash after the sell
        db.execute("UPDATE users SET cash = :cash", cash=cash + total_price)
        
        # insert the transaction into the transactions database
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)", 
                        symbol=request.form.get("symbol").upper(), user_id=session["user_id"], shares=int(request.form.get("shares")) * -1, price=usd(lookup(request.form.get("symbol"))["price"]))
    
        # redirect to the home page
        return redirect(url_for("index"))
    
    # if the "buy" button in the toolbar is clicked, show the buy page
    else:
        return render_template("sell.html")
        

@app.route("/add cash", methods=["GET", "POST"])
@login_required
def addcash():
    """Add Cash to account."""

    if request.method == "POST":
        
        # ensure that the user enters a valid amount
        if not request.form.get("amount"):
            return apology("must provide an amount to add")
        
        # ensure that the amount entered is more than 0
        if int(request.form.get("amount")) < 1:
            return apology("must enter a positive amount")
        cash = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])[0]["cash"]
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", id=session["user_id"], cash=cash + int(request.form.get("amount")))    
    
        # redirect to the home page
        return redirect(url_for("index"))
        
    else:
        return render_template("addcash.html")
