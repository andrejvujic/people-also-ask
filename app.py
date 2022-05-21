from datetime import datetime
from io import StringIO, BytesIO
import os
from flask import Flask, render_template, redirect, send_file, request
import pickle
import people_also_ask


app = Flask(__name__)


cwd = os.path.dirname(
    os.path.abspath(__file__),
)
cache_file_path = os.path.join(cwd, ".cache")


def write_cache(obj: dict) -> None:
    with open(cache_file_path, "wb") as f:
        pickle.dump(obj, f)


def read_cache() -> dict:
    with open(cache_file_path, "rb") as f:
        return pickle.load(f)


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

        return redirect(f"/getRelatedQuestions?q={q}&max={max_num_of_questions}")

    return render_template("index.html")


@app.route("/getRelatedQuestions", methods=["GET", "POST"])
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

        if request.url in cache and is_cache_valid(
            cache.get(request.url).get("time"),
        ):
            results = cache.get(request.url).get("data")
        else:
            questions = get_questions_for_query(query=query, max=max)
            results = get_results_for_questions(questions=questions)

            cache = read_cache()
            cache[request.url] = {
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

    cache = read_cache()
    results = cache.get(request.url)["data"]

    query = request.form["query"]
    max = request.form["max"]

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


if __name__ == "__main__":
    app.run()
