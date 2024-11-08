from flask import Flask, request, render_template, redirect, url_for, jsonify, session
import boto3
import uuid
from flask_cors import CORS
from datetime import datetime
from boto3.dynamodb.conditions import Attr, Key

# Create Flask application instance
app = Flask(__name__)
app.secret_key = 'supersecretkey'
CORS(app)

# Configure DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
users_table = dynamodb.Table('Users')
posts_table = dynamodb.Table('Posts')
subscriptions_table = dynamodb.Table('Subscriptions')
portfolios_table = dynamodb.Table('Portfolios')
messages_table = dynamodb.Table('Messages')

s3 = boto3.client('s3')
bucket_name = 'designerhubmedia'

"""
Created this for making timestamo more user friendly
"""
@app.template_filter('format_datetime')
def format_datetime(timestamp):
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%b %d at %I:%M %p")
    except:
        return timestamp

"""
Login route
"""
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Get user data from DynamoDB
        response = users_table.scan(FilterExpression=Attr('email').eq(email))
        users = response.get('Items')

        if users:
            user = users[0]
            if user['password'] == password:
                # Need to store user id in session for consistency
                session['user_id'] = user['UserID']
                return redirect(url_for('main', user_id=user['UserID']))
            else:
                return jsonify({'error': 'Invalid credentials. Please try again.'}), 401
        else:
            return jsonify({'error': 'User not found. Please register first.'}), 404

    return render_template('index.html')

"""
Route for registration page
"""
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = request.form['password']

        # Create unique UserID
        user_id = str(uuid.uuid4())

        # Store data in dynamoDB
        users_table.put_item(
            Item={
                'UserID': user_id,
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'password': password
            }
        )
        return redirect(url_for('login'))

    return render_template('register.html')

"""
Route for main page after login
"""
@app.route('/main/<user_id>', methods=['GET', 'POST'])
def main(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return redirect(url_for('login'))

    # Get user data
    response = users_table.get_item(Key={'UserID': user_id})
    user = response.get('Item')
    if not user:
        return jsonify({'error': 'User not found.'}), 404

    if request.method == 'POST':
        # Creating a new post
        content = request.form['content']
        post_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Store post in DynamoDB
        posts_table.put_item(
            Item={
                'PostID': post_id,
                'UserID': user_id,
                'content': content,
                'timestamp': timestamp
            }
        )

        # Store post image in S3
        if 'image' in request.files:
            image = request.files['image']
            s3_key = f'posts/{post_id}.jpg'
            s3.upload_fileobj(image, bucket_name, s3_key)

    # Get user posts
    posts_response = posts_table.scan(FilterExpression=Attr('UserID').eq(user_id))
    posts = posts_response.get('Items')

    # Sort posts by timestamp in descending order (newest first)
    posts.sort(key=lambda x: x['timestamp'], reverse=True)

    # Generate presigned URLs for each post image
    for post in posts:
        if 'PostID' in post:
            s3_key = f'posts/{post["PostID"]}.jpg'
            post['image_url'] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': s3_key},
                ExpiresIn=3600
            )

    # Get user portfolio items
    portfolio_response = portfolios_table.query(
        KeyConditionExpression=Key('UserID').eq(user_id)
    )
    portfolio_items = portfolio_response.get('Items', [])

    # Create presigned URLs for each portfolio image
    for item in portfolio_items:
        if 'ImageKey' in item:
            item['image_url'] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': item['ImageKey']},
                ExpiresIn=3600
            )

    # Get users subscriptions
    subscriptions_response = subscriptions_table.query(
        KeyConditionExpression=Key('SubscriberID').eq(user_id)
    )
    subscriptions = subscriptions_response.get('Items', [])

    # Add user details to each subscription for display
    for subscription in subscriptions:
        subscribed_user = users_table.get_item(Key={'UserID': subscription['SubscribedToID']}).get('Item')
        if subscribed_user:
            subscription['first_name'] = subscribed_user.get('first_name', 'Unknown')
            subscription['last_name'] = subscribed_user.get('last_name', 'Unknown')

    return render_template('main.html', user=user, posts=posts, portfolio_items=portfolio_items, subscriptions=subscriptions)


"""
Route to subscribe to a user
"""
@app.route('/subscribe_user/<subscriber_id>/<subscribed_to_id>', methods=['POST'])
def subscribe_user(subscriber_id, subscribed_to_id):
    timestamp = datetime.utcnow().isoformat()
    subscriptions_table.put_item(
        Item={
            'SubscriberID': subscriber_id,
            'SubscribedToID': subscribed_to_id,
            'SubscribedTimestamp': timestamp
        }
    )
    return redirect(url_for('main', user_id=subscriber_id))

"""
Route for retrieving users to subscribe to
"""
@app.route('/subscriptions/<user_id>', methods=['GET'])
def get_subscriptions(user_id):
    response = subscriptions_table.query(
        KeyConditionExpression=Key('SubscriberID').eq(user_id)
    )
    subscriptions = response.get('Items', [])
    return jsonify(subscriptions), 200

"""
Route for searching users
"""
@app.route('/search_users', methods=['POST'])
def search_users():
    try:
        search_query = request.form.get('search_query', '').strip()
        if not search_query:
            return jsonify({'error': 'Search query cannot be empty'}), 400

        search_terms = search_query.lower().split()
        
        response = users_table.scan()
        all_users = response.get('Items', [])
        
        matched_users = []
        for user in all_users:
            user_full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".lower()
            user_email = user.get('email', '').lower()
            
            if all(term in user_full_name or term in user_email for term in search_terms):
                matched_users.append(user)

        current_user_id = session.get('user_id')
        if not current_user_id:
            return jsonify({'error': 'User ID not found in session'}), 400

        return render_template('user_search_results.html', 
                            users=matched_users, 
                            current_user_id=current_user_id)

    except Exception as e:
        return jsonify({'error': 'Internal Server Error', 'details': str(e)}), 500

"""
Route for viewing a subscribed user's posts
"""
@app.route('/view_user_posts/<user_id>')
def view_user_posts(user_id):
    try:
        # Get user data to make sure the user exists
        user_response = users_table.get_item(Key={'UserID': user_id})
        user = user_response.get('Item')
        if not user:
            return jsonify({'error': 'User not found.'}), 404

        # Get posts of the user
        posts_response = posts_table.scan(FilterExpression=Attr('UserID').eq(user_id))
        posts = posts_response.get('Items')

        # Generate presigned URLs for each post image, similar to above.
        for post in posts:
            if 'PostID' in post:
                s3_key = f'posts/{post["PostID"]}.jpg'
                post['image_url'] = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': 'designerhubmedia', 'Key': s3_key},
                    ExpiresIn=3600
                )

        return render_template('user_posts.html', user=user, posts=posts)

    except Exception as e:
        # Return error for better debugging. Helped with server problem I was having
        return jsonify({'error': 'Internal Server Error', 'details': str(e)}), 500

"""
Route for managing the portfoilo stuff
"""
@app.route('/manage_portfolio/<user_id>', methods=['GET', 'POST'])
def manage_portfolio(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # For adding new portfolio item
        title = request.form['title']
        description = request.form['description']

        # For image upload to S3
        if 'image' in request.files:
            image = request.files['image']
            portfolio_id = str(uuid.uuid4())
            s3_key = f'portfolios/{user_id}/{portfolio_id}.jpg'

            # Upload image to S3
            s3.upload_fileobj(image, bucket_name, s3_key)

            # Add item to DynamoDB
            portfolios_table.put_item(
                Item={
                    'UserID': user_id,
                    'PortfolioID': portfolio_id,
                    'Title': title,
                    'Description': description,
                    'ImageKey': s3_key,
                    'Timestamp': datetime.utcnow().isoformat()
                }
            )
        return redirect(url_for('manage_portfolio', user_id=user_id))

    # Retrieve portfolio items for user
    response = portfolios_table.query(
        KeyConditionExpression=Key('UserID').eq(user_id)
    )
    portfolio_items = response.get('Items', [])

    # Create presigned URLs for each portfolio image
    for item in portfolio_items:
        if 'ImageKey' in item:
            item['image_url'] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': item['ImageKey']},
                ExpiresIn=3600
            )

    return render_template('manage_portfolio.html', portfolio_items=portfolio_items, user_id=user_id)

"""
This route for deleting portfolio items
"""
@app.route('/delete_portfolio/<user_id>/<portfolio_id>', methods=['POST'])
def delete_portfolio(user_id, portfolio_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return redirect(url_for('login'))

    # Get the portfolio item from DynamoDB
    response = portfolios_table.get_item(
        Key={
            'UserID': user_id,
            'PortfolioID': portfolio_id
        }
    )
    item = response.get('Item')

    if item:
        # Delete image from S3
        s3_key = item['ImageKey']
        s3.delete_object(Bucket=bucket_name, Key=s3_key)

        # Delete item from dynamoDB
        portfolios_table.delete_item(
            Key={
                'UserID': user_id,
                'PortfolioID': portfolio_id
            }
        )
    return redirect(url_for('manage_portfolio', user_id=user_id))


"""
Route to send message to another user
"""
@app.route('/send_message/<receiver_id>', methods=['POST'])
def send_message(receiver_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    sender_id = session['user_id']
    message_content = request.form['message_content']
    timestamp = datetime.utcnow().isoformat()

    # Store the message in dynamoDB
    message_id = str(uuid.uuid4())
    messages_table.put_item(
        Item={
            'MessageID': message_id,
            'SenderID': sender_id,
            'ReceiverID': receiver_id,
            'Content': message_content,
            'Timestamp': timestamp
        }
    )

    # Redirect back to the user's posts page
    return redirect(url_for('main', user_id=session['user_id']))

"""
Route for viewing received messages
"""
@app.route('/view_messages/<user_id>', methods=['GET'])
def view_messages(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return redirect(url_for('login'))

    # Get the received messages
    received_response = messages_table.scan(FilterExpression=Attr('ReceiverID').eq(user_id))
    received_messages = received_response.get('Items', [])

    # Get the sent messages
    sent_response = messages_table.scan(FilterExpression=Attr('SenderID').eq(user_id))
    sent_messages = sent_response.get('Items', [])

    # Combine messages and add user info. Better and more user friendly, like a conversation or chat
    all_messages = received_messages + sent_messages
    
    # Sort messages by timestamp
    all_messages.sort(key=lambda x: x['Timestamp'], reverse=True)

    # Get user info for each message that sent/received
    for message in all_messages:
        sender = users_table.get_item(Key={'UserID': message['SenderID']}).get('Item')
        receiver = users_table.get_item(Key={'UserID': message['ReceiverID']}).get('Item')
        if sender:
            message['sender_name'] = f"{sender.get('first_name', 'Unknown')} {sender.get('last_name', 'Unknown')}"
        if receiver:
            message['receiver_name'] = f"{receiver.get('first_name', 'Unknown')} {receiver.get('last_name', 'Unknown')}"
        message['is_sent'] = message['SenderID'] == user_id

    return render_template('view_messages.html', messages=all_messages, user_id=user_id)

# Error handler for resource not found. Helped when having problems.
@app.errorhandler(404)
def resource_not_found(e):
    return jsonify(error=str(e)), 404

# Error handler for server errors. Used this when i was having problems also.
@app.errorhandler(500)
def server_error(e):
    return jsonify(error=str(e)), 500

# Main function to run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)