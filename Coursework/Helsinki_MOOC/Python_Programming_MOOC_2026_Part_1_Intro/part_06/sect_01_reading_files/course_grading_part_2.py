# write your solution here
student_info = input("Student information: ")
exercise_data = input("Exercises completed: ")
exam_data = input("Exam points: ")


student_dict = {}
exercises_dict = {}
exam_dict = {}

with open(student_info) as file:
    for line in file:
        parts = line.strip().split(';')
        if parts[0] == 'id':
            continue
        student_dict[parts[0]] = (parts[1], parts[2])

with open(exercise_data) as file:
    for line in file:
        parts = line.strip().split(';')
        if parts[0] == 'id':
            continue
        exercises_dict[parts[0]] = sum(map(int, parts[1:]))

with open(exam_data) as file:
    for line in file:
        parts = line.strip().split(";")
        if parts[0] == 'id':
            continue
        exam_dict[parts[0]] = sum(map(int, parts[1:]))

def grade_of_points(points):
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

for id, (first, last) in student_dict.items():
    if id in exercises_dict and id in exam_dict:
        exam_points = exam_dict[id]
        exercises_points = exercises_dict[id]//4
        total_points = exam_points + exercises_points
        grade = grade_of_points(total_points)
        print(f"{first} {last} {grade}")