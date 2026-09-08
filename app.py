from flask import Flask, render_template, request, redirect, session
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = "curio_secret_key"

# Connect to MySQL
db = mysql.connector.connect(
    host=os.getenv("MYSQLHOST", os.getenv("MYSQL_HOST")),
    port=int(os.getenv("MYSQLPORT", "3306")),
    user=os.getenv("MYSQLUSER", os.getenv("MYSQL_USER")),
    password=os.getenv("MYSQLPASSWORD", os.getenv("MYSQL_PASSWORD")),
    database=os.getenv("MYSQLDATABASE", os.getenv("MYSQL_DATABASE"))
)
cursor = db.cursor()


# Home Page
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/welcome")

    return render_template("index.html")


@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/start", methods=["POST"])
def start():
    name = request.form.get("name")
    level = request.form.get("level")

    # Check if the user already exists
    cursor.execute("""
        SELECT user_id
        FROM users
        WHERE name = %s
        LIMIT 1
    """, (name,))

    existing_user = cursor.fetchone()

    if existing_user:
        # Use the existing user's ID
        user_id = existing_user[0]

        # Update their selected learning level
        cursor.execute("""
            UPDATE users
            SET level = %s
            WHERE user_id = %s
        """, (level, user_id))

        db.commit()

    else:
        # Create a new user
        cursor.execute("""
            INSERT INTO users (name, level)
            VALUES (%s, %s)
        """, (name, level))

        db.commit()

        user_id = cursor.lastrowid

    # Store user information in session
    session["user_id"] = user_id
    session["name"] = name
    session["level"] = level

    return redirect("/")

# Topic Library
@app.route("/topics")
def topics():

    level = request.args.get("level")

    cursor.execute("""
        SELECT topic_id, title, category, description
        FROM topics
        ORDER BY topic_id
    """)

    topic_list = cursor.fetchall()

    return render_template(
        "topics.html",
        topics=topic_list,
        level=level
    )

@app.route("/search")
def search():
    query = request.args.get("q", "")
    level = session.get("level", "Beginner")
    user_id = session.get("user_id")

    cursor.execute("""
        SELECT topic_id, title, category, description
        FROM topics
        WHERE title LIKE %s
        ORDER BY topic_id
    """, ("%" + query + "%",))

    results = cursor.fetchall()

    # Save searches for the current user
    if user_id:
        for result in results:
            cursor.execute("""
                INSERT INTO search_history
                (user_id, topic_id, search_date)
                VALUES (%s, %s, CURDATE())
            """, (user_id, result[0]))

        db.commit()

    return render_template(
        "search.html",
        results=results,
        query=query,
        level=level
    )

# Surprise Me
@app.route("/surprise")
def surprise():
    level = session.get("level", "Beginner")

    cursor.execute("""
        SELECT topic_id
        FROM topics
        ORDER BY RAND()
        LIMIT 1
    """)

    random_topic = cursor.fetchone()

    return render_template(
        "surprise.html",
        topic_id=random_topic[0],
        level=level
    )

# Individual Topic Page
@app.route("/topic/<int:topic_id>")
def topic(topic_id):

    level = request.args.get("level")

    # Get topic information
    cursor.execute("""
        SELECT topic_id, title, category, description, fun_fact
        FROM topics
        WHERE topic_id = %s
    """, (topic_id,))

    topic_data = cursor.fetchone()

    # Get explanation according to selected level
    cursor.execute("""
        SELECT explanation
        FROM topic_content
        WHERE topic_id = %s AND level = %s
        LIMIT 1
    """, (topic_id, level))

    content = cursor.fetchone()

    # Get Rabbit Hole topics
    cursor.execute("""
        SELECT topics.topic_id, topics.title
        FROM rabbit_hole
        JOIN topics
        ON rabbit_hole.related_topic_id = topics.topic_id
        WHERE rabbit_hole.topic_id = %s
    """, (topic_id,))

    related_topics = cursor.fetchall()

    return render_template(
        "topic.html",
        topic=topic_data,
        explanation=content,
        level=level,
        related_topics=related_topics
    )
@app.route("/quiz/<int:topic_id>")
def quiz(topic_id):
    level = request.args.get("level", "Beginner")

    # Find the category of the selected topic
    cursor.execute("""
        SELECT category
        FROM topics
        WHERE topic_id = %s
    """, (topic_id,))

    category_result = cursor.fetchone()

    if not category_result:
        return "Topic not found"

    category = category_result[0]

    # Get 5 random questions from the same category
    cursor.execute("""
        SELECT quiz_questions.question_id,
               quiz_questions.question,
               quiz_questions.option_a,
               quiz_questions.option_b,
               quiz_questions.option_c,
               quiz_questions.option_d
        FROM quiz_questions
        JOIN topics
        ON quiz_questions.topic_id = topics.topic_id
        WHERE topics.category = %s
        ORDER BY RAND()
        LIMIT 5
    """, (category,))

    questions = cursor.fetchall()

    return render_template(
        "quiz.html",
        questions=questions,
        topic_id=topic_id,
        level=level
    )
# Submit Quiz
@app.route("/submit_quiz", methods=["POST"])
def submit_quiz():
    topic_id = request.form.get("topic_id")
    level = request.form.get("level")
    user_id = session.get("user_id")
    question_ids = request.form.getlist("question_ids")

    if not user_id:
        return redirect("/welcome")

    score = 0

    for question_id in question_ids:
        user_answer = request.form.get("question_" + question_id)

        cursor.execute("""
            SELECT correct_option
            FROM quiz_questions
            WHERE question_id = %s
        """, (question_id,))

        result = cursor.fetchone()

        if result and user_answer == result[0]:
            score += 1

    total = len(question_ids)

    # Save quiz result for the current user
    cursor.execute("""
        INSERT INTO quiz_results
        (user_id, topic_id, score, total_questions, quiz_date)
        VALUES (%s, %s, %s, %s, CURDATE())
    """, (user_id, topic_id, score, total))

    db.commit()

    return render_template(
        "quiz_result.html",
        score=score,
        total=total,
        topic_id=topic_id,
        level=level
    )
@app.route("/add_interest", methods=["POST"])
def add_interest():
    topic_id = request.form.get("topic_id")
    user_id = session.get("user_id")

    if not user_id:
        return redirect("/welcome")

    cursor.execute("""
        SELECT interest_id
        FROM interests
        WHERE user_id = %s AND topic_id = %s
    """, (user_id, topic_id))

    existing = cursor.fetchone()

    if not existing:
        cursor.execute("""
            INSERT INTO interests
            (user_id, topic_id, date_added)
            VALUES (%s, %s, CURDATE())
        """, (user_id, topic_id))

        db.commit()

    return redirect(
        "/topic/" + topic_id +
        "?level=" + session.get("level", "Beginner")
    )

@app.route("/interests")
def interests():
    user_id = session.get("user_id")
    level = session.get("level", "Beginner")

    if not user_id:
        return redirect("/welcome")

    cursor.execute("""
        SELECT topics.topic_id,
               topics.title,
               topics.category,
               topics.description
        FROM interests
        JOIN topics
        ON interests.topic_id = topics.topic_id
        WHERE interests.user_id = %s
        ORDER BY interests.date_added DESC
    """, (user_id,))

    saved_topics = cursor.fetchall()

    return render_template(
        "interests.html",
        topics=saved_topics,
        level=level
    )

@app.route("/trending")
def trending():
    level = session.get("level", "Beginner")

    cursor.execute("""
        SELECT
            topics.topic_id,
            topics.title,
            topics.category,
            COUNT(search_history.search_id) AS search_count
        FROM search_history
        JOIN topics
        ON search_history.topic_id = topics.topic_id
        GROUP BY topics.topic_id, topics.title, topics.category
        ORDER BY search_count DESC
        LIMIT 10
    """)

    trending_topics = cursor.fetchall()

    return render_template(
        "trending.html",
        topics=trending_topics,
        level=level
    )

@app.route("/stats")
def stats():
    user_id = session.get("user_id")

    if not user_id:
        return redirect("/welcome")

    # Number of quizzes attempted
    cursor.execute("""
        SELECT COUNT(*)
        FROM quiz_results
        WHERE user_id = %s
    """, (user_id,))

    quizzes = cursor.fetchone()[0]

    # Average quiz score percentage
    cursor.execute("""
        SELECT AVG((score * 100.0) / total_questions)
        FROM quiz_results
        WHERE user_id = %s
    """, (user_id,))

    average_score = cursor.fetchone()[0]

    if average_score is None:
        average_score = 0

    # Number of saved interests
    cursor.execute("""
        SELECT COUNT(*)
        FROM interests
        WHERE user_id = %s
    """, (user_id,))

    interests_count = cursor.fetchone()[0]

    # Number of different topics searched
    cursor.execute("""
        SELECT COUNT(DISTINCT topic_id)
        FROM search_history
        WHERE user_id = %s
    """, (user_id,))

    topics_explored = cursor.fetchone()[0]

    return render_template(
        "stats.html",
        quizzes=quizzes,
        average_score=round(average_score, 1),
        interests_count=interests_count,
        topics_explored=topics_explored
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/welcome")

if __name__ == "__main__":
    app.run(debug=True)