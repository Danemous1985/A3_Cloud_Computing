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

s3 = boto3.client('s3')

# Route for home page (login page)
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

# Route for registration page
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

# Route for main page after login
@app.route('/main/<user_id>', methods=['GET', 'POST'])
def main(user_id):
    if 'user_id' in session:
        print(f"Session User ID: {session['user_id']}")
    else:
        print("No user ID found in session.")

    response = users_table.get_item(Key={'UserID': user_id})
    user = response.get('Item')
    if not user:
        return jsonify({'error': 'User not found.'}), 404

    if request.method == 'POST':
        # Creating a new post here
        content = request.form['content']
        post_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Store post in dynamoDB
        posts_table.put_item(
            Item={
                'PostID': post_id,
                'UserID': user_id,
                'content': content,
                'timestamp': timestamp
            }
        )

        # Store post image in S3 BUCKET
        if 'image' in request.files:
            image = request.files['image']
            bucket_name = 'designerhubmedia'
            # Store in the 'posts' folder
            s3_key = f'posts/{post_id}.jpg'
            s3.upload_fileobj(image, bucket_name, s3_key)

    # Get user posts
    posts_response = posts_table.scan(FilterExpression=Attr('UserID').eq(user_id))
    posts = posts_response.get('Items')

    # Generate presigned URLs for each post image. This was problem and had to use presigned URL's to function
    for post in posts:
        if 'PostID' in post:
            s3_key = f'posts/{post["PostID"]}.jpg'
            post['image_url'] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': 'designerhubmedia', 'Key': s3_key},
                  # URL valid for 1 hour but regenerates.
                ExpiresIn=3600
            )

    # Get users subscriptions
    subscriptions_response = subscriptions_table.query(
        KeyConditionExpression=Key('SubscriberID').eq(user_id)
    )
    subscriptions = subscriptions_response.get('Items', [])

    # Add user details to each subscription for display. Very difficult this section.
    for subscription in subscriptions:
        subscribed_user = users_table.get_item(Key={'UserID': subscription['SubscribedToID']}).get('Item')
        if subscribed_user:
            subscription['first_name'] = subscribed_user.get('first_name', 'Unknown')
            subscription['last_name'] = subscribed_user.get('last_name', 'Unknown')

    return render_template('main.html', user=user, posts=posts, subscriptions=subscriptions)

# Route to subscribe to a user
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

# Route for retrieving users to subscribe to
@app.route('/subscriptions/<user_id>', methods=['GET'])
def get_subscriptions(user_id):
    response = subscriptions_table.query(
        KeyConditionExpression=Key('SubscriberID').eq(user_id)
    )
    subscriptions = response.get('Items', [])
    return jsonify(subscriptions), 200

# Route for searching users
@app.route('/search_users', methods=['POST'])
def search_users():
    try:
        search_query = request.form.get('search_query', '').strip()

        if not search_query:
            return jsonify({'error': 'Search query cannot be empty'}), 400

        # Search for users in synamoDB
        response = users_table.scan(
            FilterExpression=Attr('first_name').contains(search_query) | 
                             Attr('last_name').contains(search_query) |
                             Attr('email').contains(search_query)
        )

        users = response.get('Items', [])

        # Retrieve user_id from session. Need this for consistency across pages
        current_user_id = session.get('user_id')

        if not current_user_id:
            return jsonify({'error': 'User ID not found in session'}), 400

        # Render the template, passing the current_user_id. Needed this for subscription page
        return render_template('user_search_results.html', users=users, current_user_id=current_user_id)

    except Exception as e:
        # This for debugging because I was having alot of problems
        return jsonify({'error': 'Internal Server Error', 'details': str(e)}), 500

# Route for viewing a subscribed user's posts
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

# Error handler for resource not found
@app.errorhandler(404)
def resource_not_found(e):
    return jsonify(error=str(e)), 404

# Error handler for server errors
@app.errorhandler(500)
def server_error(e):
    return jsonify(error=str(e)), 500

# Main function to run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
