def grade_from_points(exam_points, total_points):
    if exam_points < 10:
        return 0
    if total_points < 15:
        return 0
    if total_points < 18:
        return 1
    if total_points < 21:
        return 2
    if total_points < 24:
        return 3
    if total_points < 28:
        return 4
    return 5

students = 0
pass_count = 0
total_points_sum = 0
grades = [0] * 6

while True:
    line = input()
    if line == "":
        break

    nums = line.split()
    if len(nums) < 2:
        continue
    exam = int(nums[0])
    exercises = int(nums[1])

    exercise_points = exercises // 10
    total = exam + exercise_points

    grade = grade_from_points(exam, total)

    students +=1
    total_points_sum += total
    grades[grade] += 1
    if grade > 0:
        pass_count += 1

print("Statistics:")
avg = total_points_sum / students if students > 0 else 0
pass_percentage = (pass_count / students * 100) if students > 0 else 0
print(f"Points average: {avg:.1f}")
print(f"Pass percentage: {pass_percentage:.1f}")
print("Grade distribution:")
for i in range(5, -1, -1):
    print(f"{i}: {'*' * grades[i]}")