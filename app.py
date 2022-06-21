from crypt import methods
from datetime import datetime
from io import StringIO, BytesIO
import os
from flask import Flask, render_template, redirect, send_file, request
import pickle
from random import choice
import people_also_ask


app = Flask(__name__)

ROOT = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(ROOT, "static")

if not os.path.exists(UPLOAD_FOLDER):
    os.mkdir(UPLOAD_FOLDER)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

cwd = os.path.dirname(
    os.path.abspath(__file__),
)
cache_file_path = os.path.join(cwd, ".cache")


def write_cache(obj: dict) -> None:
    with open(cache_file_path, "wb") as f:
        pickle.dump(obj, f)


def get_random_id(length: int = 10) -> str:
    _ = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    return "".join([str(choice(_)) for i in range(length)])


def read_cache() -> dict:
    with open(cache_file_path, "rb") as f:
        return pickle.load(f)


def get_request_cache_id(query: str, max: int):
    return f"{query}-{max}"


if not os.path.isfile(cache_file_path):
    write_cache(
        dict({}),
    )


def is_cache_valid(time: datetime) -> bool:
    now = datetime.utcnow()
    difference = now - time
    return difference.seconds < 3600


def get_questions_for_query(query: str, max: int) -> list[str]:
    try:
        return people_also_ask.get_related_questions(
            query, max_nb_questions=max,
        )
    except Exception:
        return []


def get_results_for_questions(questions: list[str]) -> list[dict]:
    results = []

    for q in questions:
        a = people_also_ask.get_answer(q)

        if a["has_answer"]:
            results.append(
                {
                    "id": q.replace(" ", "-"),
                    "question": q,
                    "answer": a["response"].replace("\n", "<br>"),
                    "link": a["link"],
                }
            )

    return results


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        q = request.form["query-input"]
        q = str(q).strip().replace(" ", "-")

        max_num_of_questions = request.form["number-input"]

        return redirect(f"/single/getRelatedQuestions?q={q}&max={max_num_of_questions}")

    return render_template("index.html")


@app.route("/single/getRelatedQuestions", methods=["GET", "POST"])
def getRelatedQuestions():
    if request.method == "GET":
        args = request.args
        query = args.get("q")

        max = args.get("max")
        max = int(max) if max else 10

        if not query:
            return render_template("error.html", message="You must provide a query.")
        else:
            query = query.replace("-", " ")

        cache = read_cache()
        cache_id = get_request_cache_id(query, max)

        if cache_id in cache and is_cache_valid(
            cache.get(cache_id).get("time"),
        ):
            results = cache.get(cache_id).get("data")
        else:
            questions = get_questions_for_query(query=query, max=max)
            results = get_results_for_questions(questions=questions)

            cache = read_cache()
            cache[cache_id] = {
                "data": results,
                "time": datetime.utcnow(),
            }
            write_cache(cache)

        if len(results):
            return render_template(
                "results.html", request_url=request.url, query=query, max=max, results=results, len_=len(results),
            )

        return render_template(
            "error.html", request_url=request.url, message=f"No related questions for {query}, please try again later...",
        )

    query = request.form["query"]
    max = request.form["max"]

    cache = read_cache()
    cache_id = get_request_cache_id(query, max)

    results = cache.get(cache_id)["data"]

    if not query or not max or not results:
        return render_template("error.html", message="We encountered an error while trying to save the site...")

    strIO = StringIO()
    strIO.write(
        render_template(
            'results.html', request_url=request.url, in_download_mode=True, query=query, max=max, results=results, len_=len(results),
        ),
    )

    memory = BytesIO()
    memory.write(
        strIO.getvalue().encode(),
    )
    memory.seek(0)

    strIO.close()

    return send_file(
        memory, attachment_filename=f"{query.replace(' ', '-')}.html", as_attachment=True,
    )


@app.route("/multiple", methods=["GET", "POST"])
def multiple():
    if request.method == "GET":
        return render_template(
            "multiple.html",
        )

    session = get_random_id()

    queries = request.form["queries-input"]
    queries = queries.splitlines()

    session_dir_path = os.path.join(
        ROOT, UPLOAD_FOLDER, session,
    )

    if not os.path.isdir(session_dir_path):
        os.mkdir(session_dir_path)

    queries_file_path = os.path.join(
        session_dir_path, ".queries",
    )

    with open(queries_file_path, "wb") as f:
        pickle.dump(queries, f)

    max_num_of_questions = request.form["number-input"]
    delay_between_searching = request.form["delay-input"]

    return redirect(
        f"/multiple/getRelatedQuestions?session={session}&index=1&max={max_num_of_questions}&delay={delay_between_searching}"
    )


@app.route("/multiple/getRelatedQuestions", methods=["GET"])
def multipleGetRelatedQuestions():
    args = request.args

    session = args.get("session")

    index = int(
        args.get("index"),
    )

    max = args.get("max")
    delay = args.get("delay")

    session_dir_path = os.path.join(
        ROOT, UPLOAD_FOLDER, session,
    )

    if not os.path.isdir(session_dir_path):
        os.mkdir(session_dir_path)

    queries_file_path = os.path.join(
        session_dir_path, ".queries",
    )

    queries = []
    with open(queries_file_path, "rb") as f:
        queries = pickle.load(f)

    query = queries[index - 1]
    query = query.strip()

    cache = read_cache()
    cache_id = get_request_cache_id(query, max)

    if cache_id in cache and is_cache_valid(
        cache.get(cache_id).get("time"),
    ):
        results = cache.get(cache_id).get("data")
    else:
        questions = get_questions_for_query(query=query, max=max)
        results = get_results_for_questions(questions=questions)

        cache = read_cache()
        cache[cache_id] = {
            "data": results,
            "time": datetime.utcnow(),
        }
        write_cache(cache)

    strIO = StringIO()
    strIO.write(
        render_template(
            'results.html', request_url=request.url, in_download_mode=True, query=query, max=max, results=results, len_=len(results),
        ),
    )

    memory = BytesIO()
    memory.write(
        strIO.getvalue().encode(),
    )
    memory.seek(0)

    strIO.close()

    results_path = os.path.join(
        session_dir_path, "results",
    )
    if not os.path.isdir(results_path):
        os.mkdir(results_path)

    file_name = f"{query.replace(' ', '-')}.html"
    file_path = os.path.join(
        results_path, file_name,
    )

    with open(file_path, "wb") as f:
        f.write(
            memory.getbuffer(),
        )

    return "Done"


if __name__ == "__main__":
    app.run()
