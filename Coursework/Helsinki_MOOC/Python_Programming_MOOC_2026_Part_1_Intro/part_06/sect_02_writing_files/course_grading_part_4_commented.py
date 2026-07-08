"""
Commented copy of `course_grading_part_4.py` showing the fixes and logic
that make the program work with the course tests.

Changelog / summary of fixes applied across edits:
- Fixed broken file open and variable-name bugs in original file.
- Made CSV parsing robust for files that have multiple numeric columns
  (e.g. exercises: e1;e2;e3... and exams: e1;e2;e3...). The correct behavior
  is to sum the numeric columns per row to compute total exercise/exam points.
- Ensured `read_file` checks are case-insensitive (use lowercased filename
  to detect file type based on name substrings like "students", "exercises",
  "exam_points", "course").
- `students` parsing returns a dict mapping id -> (first, last).
- `exercises` parsing returns a dict mapping id -> total_exercise_count.
- `exams` parsing returns a dict mapping id -> total_exam_points.
- `write_results` now uses the parameters passed in (students, exercises, exams,
  course, results filename) and builds both `results.txt` and `results.csv`.
  The CSV lines are `id;name;grade` as expected by the tests.
- Format of the header line in `results.txt` is exactly "{course_name}, {credits} credits"
  (no extra commas), matching the expected output.
- Program executes on import and reads filenames via `input()` so the test harness
  can patch `input()` and run the program when the module is reloaded.

The rest of this file is the working program with explanatory comments inline.
"""

# --- helper: read different expected input files ---
def read_file(file_name):
    """Parse a file based on its name.

    - If filename contains "students": parse id;first;last and return dict
      id -> (first, last)
    - If filename contains "exercises": parse id;e1;e2;... and sum exercise counts
      to return dict id -> total_exercises
    - If filename contains "exam_points": parse id;p1;p2;... and sum exam points
      to return dict id -> total_exam_points
    - If filename contains "course": parse lines like "name: Introduction..."
      and return a list [course_name, credits]

    The function uses a case-insensitive check to detect file type.
    """
    lower_name = file_name.lower()

    # Students file: id;first;last
    if "students" in lower_name:
        students = {}
        with open(file_name) as f:
            for line in f:
                line = line.strip()
                parts = line.split(";")
                # skip header
                if parts[0] == "id":
                    continue
                # store tuple (first, last)
                students[parts[0]] = (parts[1], parts[2])
        return students

    # Exercises file: id;e1;e2;... -> sum exercise counts
    if "exercises" in lower_name:
        exercises = {}
        with open(file_name) as f:
            for line in f:
                line = line.strip()
                parts = line.split(";")
                if parts[0] == "id":
                    continue
                total = 0
                # sum all exercise columns after id
                for v in parts[1:]:
                    try:
                        total += int(v)
                    except ValueError:
                        # ignore non-integer values (defensive)
                        pass
                exercises[parts[0]] = total
        return exercises

    # Exam points file: id;p1;p2;... -> sum exam points
    if "exam_points" in lower_name:
        exams = {}
        with open(file_name) as f:
            for line in f:
                line = line.strip()
                parts = line.split(";")
                if parts[0] == "id":
                    continue
                total = 0
                for v in parts[1:]:
                    try:
                        total += int(v)
                    except ValueError:
                        pass
                exams[parts[0]] = total
        return exams

    # Course info: lines like "name: Introduction to Programming"
    if "course" in lower_name:
        course_info = []
        with open(file_name) as f:
            for line in f:
                line = line.strip()
                parts = line.split(":")
                if len(parts) > 1:
                    course_info.append(parts[1].strip())
        # expected: [course_name, credits]
        return course_info


# --- grading logic ---
def grade_of_points(points):
    """Return grade based on total points.

    Thresholds copied from the exercise specification.
    """
    if points <= 14:
        return 0
    elif points <= 17:
        return 1
    elif points <= 20:
        return 2
    elif points <= 23:
        return 3
    elif points <= 27:
        return 4
    else:
        return 5


# --- output writing ---
def write_results(students, exercises, exams, course, results_file_name):
    """Build `results.txt` and `results.csv` using parsed data.

    Important details to match tests:
    - Header line must be exactly: "{course_name}, {credits} credits"
    - Column layout in `results.txt` must match spacing expected by tests. We use
      f-string alignment to keep it consistent.
    - `results.csv` contains one line per student who has both exercise and exam data,
      in the format: id;name;grade
    """
    students_grade = []
    report = ""

    # Format header precisely as expected by the tests
    report += f"{course[0]}, {course[1]} credits\n"
    report += "======================================\n"
    report += f"{'name':30}{'exec_nbr':10}{'exec_pts.':10}{'exm_pts.':10}{'tot_pts.':10}{'grade':10}\n"

    # Iterate students; only include those present in both exercises and exams
    for id, (first, last) in students.items():
        if id in exercises and id in exams:
            exam_points = exams[id]
            number_of_exercises = exercises[id]
            # exercises_points means points from exercises: totalExercises // 4
            exercises_points = number_of_exercises // 4
            total_points = exam_points + exercises_points
            grade = grade_of_points(total_points)
            full_name = first + ' ' + last
            report += f"{full_name:30}{number_of_exercises:<10}{exercises_points:<10}{exam_points:<10}{total_points:<10}{grade:<10}\n"
            # For CSV, tests expect id;name;grade
            students_grade.append([id, full_name, str(grade)])

    results_txt_file_name = results_file_name + ".txt"
    results_csv_file_name = results_file_name + ".csv"

    with open(results_txt_file_name, "w") as results_txt_file:
        results_txt_file.write(report)

    with open(results_csv_file_name, "w") as results_csv_file:
        for record in students_grade:
            line = ";".join(record) + "\n"
            results_csv_file.write(line)

    # Helpful runtime message for manual runs; harmless for tests
    print(f"Results written to files {results_txt_file_name} and {results_csv_file_name}")


# --- Run on import ---
# The course test harness imports the module and patches builtins.input(), then
# reloads the module to execute it. Therefore the program must execute on import
# and read the 4 filenames via input() calls.
student_file = input('Student information: ')
exercises_file = input('Exercises completed: ')
exam_file = input('Exam points: ')
course_file = input('Course information: ')

results_file = 'results'

# parse files using the robust reader above
students = read_file(student_file)
exercises = read_file(exercises_file)
exams = read_file(exam_file)
course = read_file(course_file)

# write outputs
write_results(students, exercises, exams, course, results_file)
