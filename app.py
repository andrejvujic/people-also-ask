from crypt import methods
from datetime import datetime
from email import message
from io import StringIO, BytesIO
import os
import shutil
from flask import Flask, render_template, redirect, send_file, request
import pickle
import zipfile
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


def open_stats(file_path: str) -> None:
    stats = dict(
        {
            "start": datetime.utcnow(),
            "succesful": 0,
            "failed": 0,
        }
    )

    write_stats(file_path, stats)


def stats_increase_succesful(file_path: str) -> None:
    stats = read_stats(file_path)
    stats["succesful"] = stats["succesful"] + 1
    write_stats(file_path, stats)


def stats_increase_failed(file_path: str) -> None:
    stats = read_stats(file_path)
    stats["failed"] = stats["failed"] + 1
    write_stats(file_path, stats)


def close_stats(file_path: str) -> None:
    stats = read_stats(file_path)
    stats["end"] = datetime.utcnow()
    write_stats(file_path, stats)


def write_stats(file_path: str, stats: dict) -> None:
    with open(file_path, "wb") as f:
        pickle.dump(
            stats,
            f,
        )


def read_stats(file_path: str) -> dict:
    with open(file_path, "rb") as f:
        return pickle.load(f)


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
    except Exception as e:
        print(e)
        return []


def get_results_for_questions(questions: list[str]) -> list[dict]:
    results = []

    if len(questions) > 0:
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
    if request.method == "GET":
        return render_template("index.html")

    form = request.form
    if form["search-type"] == "single":
        return redirect("/single")

    return redirect("/multiple")


@app.route("/single", methods=["GET", "POST"])
def single():
    if request.method == "POST":
        q = request.form["query-input"]
        q = str(q).strip().replace(" ", "-")

        max_num_of_questions = request.form["number-input"]

        return redirect(f"/single/getRelatedQuestions?q={q}&max={max_num_of_questions}")

    return render_template("single.html")


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

        if len(results):
            cache = read_cache()
            cache[cache_id] = {
                "data": results,
                "time": datetime.utcnow(),
            }
            write_cache(cache)

            return render_template(
                "single-results.html", request_url=request.url, query=query, max=max, results=results, len_=len(results),
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
            'single-results.html', request_url=request.url, in_download_mode=True, query=query, max=max, results=results, len_=len(results),
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

    stats_file_path = os.path.join(
        session_dir_path, ".stats"
    )

    open_stats(stats_file_path)

    return redirect(
        f"/multiple/getRelatedQuestions?session={session}&index=1&max={max_num_of_questions}&delay={delay_between_searching}"
    )


@app.route("/multiple/getRelatedQuestions", methods=["GET"])
def multipleGetRelatedQuestions():
    args = request.args

    session = args.get("session")

    index = args.get("index"),
    max = args.get("max"),
    delay = args.get("delay"),

    index = index[0]
    max = max[0]
    delay = delay[0]

    if not session or not index:
        return render_template("error.html", message="We encountered an error while trying to parse your request.")

    index = int(index)
    max = int(max) if max else 10
    delay = int(delay) if delay else 5

    session_dir_path = os.path.join(
        ROOT, UPLOAD_FOLDER, session,
    )

    if not os.path.isdir(session_dir_path):
        os.mkdir(session_dir_path)

    queries_file_path = os.path.join(
        session_dir_path, ".queries",
    )

    stats_file_path = os.path.join(
        session_dir_path, ".stats"
    )

    queries = []
    if not os.path.isfile(queries_file_path):
        return render_template("error.html", "We encountered an error while trying to parse the queries...")

    with open(queries_file_path, "rb") as f:
        queries = pickle.load(f)

    try:
        query = queries[index - 1]
        query = query.strip()
    except:
        close_stats(stats_file_path)
        return redirect(f"/multiple/results?session={session}")

    cache = read_cache()
    cache_id = get_request_cache_id(query, max)

    if cache_id in cache and is_cache_valid(
        cache.get(cache_id).get("time"),
    ):
        results = cache.get(cache_id).get("data")
    else:
        questions = get_questions_for_query(query=query, max=max)
        results = get_results_for_questions(questions=questions)

    if len(results):
        stats_increase_succesful(stats_file_path)

        cache = read_cache()
        cache[cache_id] = {
            "data": results,
            "time": datetime.utcnow(),
        }
        write_cache(cache)

        strIO = StringIO()
        strIO.write(
            render_template(
                'single-results.html', request_url=request.url, in_download_mode=True, query=query, max=max, results=results, len_=len(results),
            ),
        )

        memory = BytesIO()
        memory.write(
            strIO.getvalue().encode(),
        )
        memory.seek(0)

        strIO.close()

        results_path = os.path.join(
            session_dir_path, "files",
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

        return render_template("delay.html", index=index, delay=delay), {"Refresh": f"{delay}; url={request.host_url}multiple/getRelatedQuestions?session={session}&index={index + 1}&max={max}&delay={delay}"}

    stats_increase_failed(stats_file_path)
    return render_template("delay.html", index=index, delay=delay), {"Refresh": f"{delay}; url={request.host_url}multiple/getRelatedQuestions?session={session}&index={index + 1}&max={max}&delay={delay}"}


@app.route("/multiple/results", methods=["GET", "POST"])
def multipleResults():
    if request.method == "GET":
        args = request.args
        session = args.get("session")

        session_dir_path = os.path.join(
            ROOT, UPLOAD_FOLDER, session,
        )

        _cwd = os.getcwd()
        os.chdir(session_dir_path)

        if len(
            os.listdir("files")
        ) > 0:
            with zipfile.ZipFile("results.zip", "w") as f:
                files = os.listdir("files")
                for file in files:

                    f.write(
                        os.path.join("files", file), os.path.basename(file),
                    )

            os.chdir(_cwd)

            queries_file_path = os.path.join(
                session_dir_path, ".queries",
            )
            stats_file_path = os.path.join(
                session_dir_path, ".stats"
            )

            queries = []
            with open(queries_file_path, "rb") as f:
                queries = pickle.load(f)

            stats = read_stats(stats_file_path)

            duration = stats["end"] - stats["start"]
            duration = int(
                duration.total_seconds(),
            )

            return render_template("multiple-results.html", session=session, stats=stats, queries=queries, succesful=stats["succesful"], failed=stats["failed"], duration=duration)

        return render_template("error.html", message="We weren't able to find any results...")

    form = request.form
    session = form["session"]

    session_dir_path = os.path.join(
        ROOT, UPLOAD_FOLDER, session,
    )

    results_file_path = os.path.join(
        session_dir_path,
        "results.zip",
    )

    memory = None
    with open(results_file_path, "rb") as f:
        memory = BytesIO(
            f.read(),
        )

    shutil.rmtree(
        os.path.join(
            app.config["UPLOAD_FOLDER"],
            session,
        ),
        ignore_errors=True,
    )

    return send_file(
        memory, as_attachment=True, attachment_filename="results.zip",
    )


if __name__ == "__main__":
    app.run()
