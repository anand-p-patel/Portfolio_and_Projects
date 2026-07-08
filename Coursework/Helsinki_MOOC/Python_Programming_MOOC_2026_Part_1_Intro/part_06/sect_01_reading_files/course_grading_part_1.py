# write your solution here
student_info = input("Student information: ")
exercise_data = input("Exercises completed: ")

student_dict = {}
exercises_dict = {}

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
        exercises_dict[parts[0]] = sum(map(int, parts[1:8]))

for id, (first, last) in student_dict.items():
    if id in exercises_dict:
        exercises = exercises_dict[id]
        print(f"{first} {last} {exercises}")