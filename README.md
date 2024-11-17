# DesignerHub

Student Name: Dane Goulter
Student Number: S3578854

DesignerHub is a cloud-based artist centric platform that allows artists to manage their portfolios, share posts for subscribers, and connect with clients. This platform is built using AWS services like Elastic Beanstalk, DynamoDB, S3, Lambda, and API Gateway, with Flask as the backend framework.

## Preview

![DesignerHub Preview](https://i.imgur.com/9EtiaUi.jpeg) 

The above image is a preview of the application.

## Github Link

https://github.com/Danemous1985/A3_Cloud_Computing

## Link to application

https://github.com/Danemous1985/A3_Cloud_Computing

## Features

- User Registration and Login
- Portfolio Management
- Post Creation and Viewing
- User Subscription System

## Project Structure

The repository contains the following components:

- Flask App: Backend logic using Flask, deployed on AWS Elastic Beanstalk.
- AWS Services:
  - DynamoDB: For storing user, post, and subscription information.
  - S3 Storage: For media storage.
  - Lambda: For handling tasks such as image processing.
  - API Gateway: For routing API calls.

# Project Directory

The following is the structure of the project directory:

```bash
Assignment_3
├── static
│   ├── images
│   │   └── dhlogo.png
│   ├── color_palette.css
│   ├── login.css
│   ├── main.css
│   ├── manage_portfolio.css
│   ├── register.css
│   ├── user_posts.css
│   ├── user_search_results.css
│   └── view_messages.css
├── templates
│   ├── color_palette.html
│   ├── index.html
│   ├── main.html
│   ├── manage_portfolio.html
│   ├── register.html
│   ├── user_posts.html
│   ├── user_search_results.html
│   └── view_messages.html
├── app.py
├── Procfile
├── README.md
└── requirements.txt



