# Write your solution here
cohort_size = int(input("How many students on the course?"))
desired_group_size = int(input("Desired group size?"))
groups_formed = (cohort_size + desired_group_size - 1) // desired_group_size
print(f"(Number of groups formed: {groups_formed}")