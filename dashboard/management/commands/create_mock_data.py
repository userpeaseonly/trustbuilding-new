from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta, time
import random

from users.models import CustomUser, Branch
from courses.models import Course, CourseModule, Lesson, LessonSection, SectionMaterial, Test
from groups.models import Room, Group
from students.models import Student
from leads.models import Lead, PipelineStage
from employees.models import Employee
from attendance.models import Attendance, AttendanceReport


class Command(BaseCommand):
    help = 'Creates realistic mock data for testing with more randomness and variety'

    def add_arguments(self, parser):
        parser.add_argument(
            '--branches',
            type=int,
            default=3,
            help='Number of branches to create (default: 3)'
        )
        parser.add_argument(
            '--rooms-per-branch',
            type=int,
            default=8,
            help='Number of rooms per branch (default: 8)'
        )
        parser.add_argument(
            '--courses',
            type=int,
            default=8,
            help='Number of courses to create (ignored — always creates 8 fixed courses)'
        )
        parser.add_argument(
            '--teachers',
            type=int,
            default=20,
            help='Number of teachers to create (default: 20)'
        )
        parser.add_argument(
            '--students',
            type=int,
            default=100,
            help='Number of students to create (default: 100)'
        )
        parser.add_argument(
            '--groups',
            type=int,
            default=30,
            help='Number of groups to create (default: 30)'
        )
        parser.add_argument(
            '--leads',
            type=int,
            default=50,
            help='Number of leads to create (default: 50)'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting mock data creation...'))
        
        # Create branches
        branches = self.create_branches(options['branches'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(branches)} branches'))
        
        # Create rooms
        rooms = self.create_rooms(branches, options['rooms_per_branch'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(rooms)} rooms'))
        
        # Create courses
        courses = self.create_courses(options['courses'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(courses)} courses'))
        
        # Create modules and lessons with sections
        modules, lessons, sections, materials = self.create_course_content(courses)
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(modules)} modules, {len(lessons)} lessons'))
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(sections)} lesson sections with {len(materials)} materials'))
        
        # Create teachers
        teachers = self.create_teachers(branches, options['teachers'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(teachers)} teachers'))
        
        # Create students
        students = self.create_students(branches, options['students'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(students)} students'))
        
        # Create groups
        groups = self.create_groups(branches, rooms, courses, teachers, options['groups'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(groups)} groups'))
        
        # Assign students to groups
        self.assign_students_to_groups(students, groups)
        self.stdout.write(self.style.SUCCESS('✓ Assigned students to groups'))
        
        # Create leads
        leads = self.create_leads(branches, courses, options['leads'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(leads)} leads'))

        # Create attendance records and reports
        att_count, report_count = self.create_attendance_data(groups)
        self.stdout.write(self.style.SUCCESS(f'✓ Created {att_count} attendance records and {report_count} attendance reports'))

        self.stdout.write(self.style.SUCCESS('\n🎉 Mock data creation completed successfully!'))

    def create_branches(self, count):
        branches = []
        branch_data = [
            ('Chilanzar Campus', 'Tashkent, Chilanzar District, Bunyodkor Avenue 45'),
            ('Yunusabad Center', 'Tashkent, Yunusabad District, Amir Temur Street 15'),
            ('Sergeli Branch', 'Tashkent, Sergeli District, Yangi Sergeli 23'),
            ('Mirzo Ulugbek Branch', 'Tashkent, Mirzo Ulugbek District, Bogishamol Street 78'),
            ('Yakkasaray Center', 'Tashkent, Yakkasaray District, Nukus Street 12'),
            ('Mirobod Campus', 'Tashkent, Mirobod District, Aybek Street 89'),
            ('Shaykhontohur Branch', 'Tashkent, Shaykhontohur District, Labzak Street 34'),
            ('Bektemir Branch', 'Tashkent, Bektemir District, Okhangaron Road 56'),
        ]
        
        for i in range(min(count, len(branch_data))):
            name, address = branch_data[i]
            branch, created = Branch.objects.get_or_create(
                name=name,
                defaults={'address': address}
            )
            if created:
                branches.append(branch)
                self.stdout.write(f'  → {name}')
        
        return branches if branches else list(Branch.objects.all()[:count])

    def create_rooms(self, branches, rooms_per_branch):
        rooms = []
        floor_prefixes = ['1', '2', '3', '4']
        room_types = {
            'Standard': (15, 20),
            'Large': (25, 30),
            'Small': (8, 12),
            'VIP': (6, 10),
        }
        
        for branch in branches:
            for i in range(rooms_per_branch):
                floor = random.choice(floor_prefixes)
                room_num = f"{floor}{random.randint(1, 99):02d}"
                room_type = random.choice(list(room_types.keys()))
                capacity_range = room_types[room_type]
                
                room, created = Room.objects.get_or_create(
                    branch=branch,
                    name=f"{branch.name[:3].upper()}-{room_num}",
                    defaults={
                        'capacity': random.randint(*capacity_range),
                        'is_active': random.random() > 0.1,  # 90% active
                        'notes': f'{room_type} classroom'
                    }
                )
                if created:
                    rooms.append(room)
        
        return rooms

    def create_courses(self, count):
        """Always creates exactly 8 fixed named courses. The count argument is ignored."""
        course_catalog = [
            # (name, level, price, duration_months, total_lessons)
            ('Beginner',         'beginner',     500000, 3, 36),
            ('Elementary',       'beginner',     500000, 3, 36),
            ('Pre-Intermediate', 'intermediate', 1500000, 3, 36),
            ('Intermediate',     'intermediate', 1500000, 3, 36),
            ('IELTS Level 1',    'intermediate', 1500000, 3, 40),
            ('IELTS Level 2',    'advanced',     1500000, 3, 40),
            ('CEFR',             'advanced',     500000, 3, 40),
            ('Kids',             'beginner',     500000, 3, 40),
        ]

        courses = []
        for name, level, price, duration, total_lessons in course_catalog:
            course, created = Course.objects.get_or_create(
                name=name,
                defaults={
                    'level': level,
                    'price': price,
                    'currency': 'UZS',
                    'duration_months': duration,
                    'total_lessons': total_lessons,
                    'lessons_per_week': 3,
                    'is_active': True,
                    'description': f'Comprehensive {name} course for English learners',
                    'materials': 'Student Book, Workbook',
                }
            )
            if created:
                courses.append(course)
                self.stdout.write(f'  → {name}')

        return courses if courses else list(Course.objects.filter(
            name__in=[c[0] for c in course_catalog]
        ))

    def create_course_content(self, courses):
        """Create modules and lessons with structured naming (1.1, 1.2, ...) for each course.

        Structure:
        - Beginner / Elementary / Pre-Intermediate / Intermediate:
            12 units × 3 lessons = 36 lessons total.
        - IELTS Level 1 / IELTS Level 2 / CEFR / Kids:
            13 units × 3 lessons + 1 final unit (14.1) = 40 lessons total.

        Every lesson has standard sections (Warm-up, Content, Practice, Feedback).
        x.1 lessons (1.1, 2.1, 3.1, …) additionally have a Unit Test section.
        """
        all_modules = []
        all_lessons = []
        all_sections = []

        STANDARD_COURSES = {'Beginner', 'Elementary', 'Pre-Intermediate', 'Intermediate'}

        for course in courses:
            is_standard = course.name in STANDARD_COURSES
            num_full_units = 12 if is_standard else 13

            # Global sequential lesson order within this course (1, 2, 3, 4, …)
            global_lesson_order = 0

            for unit_num in range(1, num_full_units + 1):
                module = CourseModule.objects.create(
                    course=course,
                    name=f"Unit {unit_num}",
                    order=unit_num,
                    duration_weeks=4,
                )
                all_modules.append(module)

                for lesson_num in range(1, 4):  # 3 lessons per unit: .1, .2, .3
                    global_lesson_order += 1
                    title = f"{unit_num}.{lesson_num}"
                    is_test_lesson = (lesson_num == 1)  # x.1 lessons carry a unit test

                    lesson = Lesson.objects.create(
                        module=module,
                        title=title,
                        lesson_type='test' if is_test_lesson else 'lecture',
                        order=global_lesson_order,  # global sequence: 1, 2, 3, 4, 5, 6, …
                        duration_minutes=90,
                    )
                    all_lessons.append(lesson)

                    # ── Standard sections every lesson gets ──────────────────
                    section_order = 1
                    LessonSection.objects.create(
                        lesson=lesson,
                        name="Warm-up",
                        section_type='warmup',
                        order=section_order,
                        duration_minutes=10,
                    )
                    section_order += 1

                    # Content section varies by position in unit
                    if lesson_num == 1:
                        content_type, content_name = 'vocabulary', 'Vocabulary Presentation'
                    elif lesson_num == 2:
                        content_type, content_name = 'grammar', 'Grammar Focus'
                    else:
                        content_type, content_name = 'speaking', 'Speaking Practice'

                    LessonSection.objects.create(
                        lesson=lesson,
                        name=content_name,
                        section_type=content_type,
                        order=section_order,
                        duration_minutes=25,
                    )
                    section_order += 1

                    LessonSection.objects.create(
                        lesson=lesson,
                        name="Practice Activity",
                        section_type='practice',
                        order=section_order,
                        duration_minutes=35,
                    )
                    section_order += 1

                    LessonSection.objects.create(
                        lesson=lesson,
                        name="Feedback & Wrap-up",
                        section_type='feedback',
                        order=section_order,
                        duration_minutes=10,
                    )
                    section_order += 1

                    # ── Unit test section — x.1 lessons only ─────────────────
                    if is_test_lesson:
                        test = Test.objects.create(
                            name=f"{course.name} – Unit {unit_num} Test",
                            test_type='unit',
                            status='active',
                            duration=20,
                            passing_score=60,
                            course=course,
                        )
                        LessonSection.objects.create(
                            lesson=lesson,
                            name=f"Unit {unit_num} Test",
                            section_type='test',
                            test=test,
                            order=section_order,
                            duration_minutes=20,
                        )
                        section_order += 1

                    all_sections.append(lesson)  # just a count placeholder

            # Extended courses: add the 40th lesson — final assessment (14.1)
            if not is_standard:
                final_module = CourseModule.objects.create(
                    course=course,
                    name="Final Assessment",
                    order=14,
                    duration_weeks=1,
                )
                all_modules.append(final_module)

                global_lesson_order += 1
                final_lesson = Lesson.objects.create(
                    module=final_module,
                    title="14.1",
                    lesson_type='test',
                    order=global_lesson_order,
                    duration_minutes=90,
                )
                all_lessons.append(final_lesson)

                # Standard sections
                LessonSection.objects.create(lesson=final_lesson, name="Warm-up", section_type='warmup', order=1, duration_minutes=10)
                LessonSection.objects.create(lesson=final_lesson, name="Review", section_type='practice', order=2, duration_minutes=20)

                final_test = Test.objects.create(
                    name=f"{course.name} – Final Test",
                    test_type='final',
                    status='active',
                    duration=60,
                    passing_score=70,
                    course=course,
                )
                LessonSection.objects.create(
                    lesson=final_lesson,
                    name="Final Test",
                    section_type='test',
                    test=final_test,
                    order=3,
                    duration_minutes=60,
                )

        return all_modules, all_lessons, all_sections, []


    def create_teachers(self, branches, count):
        # Uzbek, Russian, and international names
        first_names = [
            'Alisher', 'Nodira', 'Davron', 'Malika', 'Sardor', 'Dilnoza', 'Jasur', 'Zarina',
            'John', 'Sarah', 'Michael', 'Emily', 'David', 'Anna', 'Robert', 'Maria',
            'Alexander', 'Olga', 'Dmitry', 'Elena', 'Igor', 'Tatiana', 'Sergey', 'Natasha'
        ]
        last_names = [
            'Karimov', 'Yusupova', 'Alimov', 'Ibragimova', 'Rahimov', 'Hasanova',
            'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia',
            'Petrov', 'Ivanov', 'Smirnov', 'Kuznetsov', 'Popov', 'Sokolov'
        ]
        specializations = [
            'English Language', 'IELTS Preparation', 'Business English', 'Korean Language',
            'Python Programming', 'Web Development', 'Data Science', 'Mobile Development',
            'Mathematics', 'Physics', 'Chemistry', 'SAT Preparation',
            'Graphic Design', 'Digital Marketing', 'Accounting'
        ]
        
        teachers = []
        for i in range(count):
            phone = f"+99890{random.randint(1000000, 9999999)}"
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            full_name = f"{first_name} {last_name}"
            
            user, created = CustomUser.objects.get_or_create(
                phone_number=phone,
                defaults={
                    'full_name': full_name,
                    'is_teacher': True,
                    'email': f"{first_name.lower()}.{last_name.lower()}@imaan.uz"
                }
            )
            
            if created:
                user.set_password('50L544k@')
                user.save()
                
                # Create employee record with realistic data
                hire_days_ago = random.randint(30, 1460)  # 1 month to 4 years
                Employee.objects.create(
                    user=user,
                    branch=random.choice(branches),
                    hire_date=timezone.now().date() - timedelta(days=hire_days_ago),
                    employment_type=random.choice(['full_time', 'full_time', 'full_time', 'part_time']),
                    salary=random.randint(4000000, 12000000),
                    currency='UZS',
                    payment_frequency='monthly',
                    specialization=random.choice(specializations),
                    is_active=random.random() > 0.05,  # 95% active
                    education=random.choice(['Bachelor', 'Master', 'PhD']),
                    experience=f"{hire_days_ago // 365} years teaching experience"
                )
                teachers.append(user)
                
        return teachers

    def create_students(self, branches, count):
        first_names = [
            'Aziza', 'Bekzod', 'Dinara', 'Eldor', 'Farida', 'Gulnora', 'Hamid', 'Iroda',
            'Alex', 'Chris', 'Sam', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley',
            'Ivan', 'Svetlana', 'Andrey', 'Katya', 'Maxim', 'Yulia'
        ]
        last_names = [
            'Tursunov', 'Sharipova', 'Ergashev', 'Nazarova', 'Umarov', 'Rahmanova',
            'Anderson', 'Thomas', 'Jackson', 'White', 'Harris', 'Martin',
            'Volkov', 'Morozova', 'Lebedev', 'Novikova'
        ]
        
        students = []
        for i in range(count):
            # Use a counter-based suffix to guarantee unique phone numbers per run
            phone = f"+998910{i:07d}"
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            full_name = f"{first_name} {last_name}"
            
            user, created = CustomUser.objects.get_or_create(
                phone_number=phone,
                defaults={
                    'full_name': full_name,
                    'is_student': True,
                    'email': f"{first_name.lower()}{i}@email.com" if random.random() > 0.3 else ''
                }
            )
            
            if created:
                user.set_password('password123')
                user.save()
                
                # More realistic status distribution (no 'lead' — students are enrolled)
                status_weights = [
                    ('active', 75),
                    ('frozen', 8),
                    ('left', 10),
                    ('archived', 7)
                ]
                status = random.choices(
                    [s[0] for s in status_weights],
                    weights=[s[1] for s in status_weights]
                )[0]
                
                # Payment status based on student status
                if status == 'active':
                    payment_status = random.choices(
                        ['paid', 'partial', 'debtor'],
                        weights=[65, 25, 10]
                    )[0]
                else:
                    payment_status = 'paid'
                
                enrollment_days_ago = random.randint(1, 730)  # Up to 2 years
                Student.objects.create(
                    user=user,
                    branch=random.choice(branches),
                    status=status,
                    payment_status=payment_status,
                    enrollment_date=timezone.now().date() - timedelta(days=enrollment_days_ago),
                    notes=f'Enrolled {enrollment_days_ago} days ago' if random.random() > 0.7 else ''
                )
                students.append(Student.objects.get(user=user))
        
        return students

    def create_groups(self, branches, rooms, courses, teachers, count):
        groups = []
        day_types = ['odd', 'even', 'daily']
        
        # More diverse time slots covering full day
        time_slots = [
            (time(7, 0), time(8, 30)),   # Early morning
            (time(8, 30), time(10, 0)),  # Morning
            (time(9, 0), time(10, 30)),
            (time(10, 0), time(11, 30)),
            (time(10, 30), time(12, 0)),
            (time(11, 0), time(12, 30)), # Midday
            (time(12, 0), time(13, 30)),
            (time(13, 0), time(14, 30)), # Afternoon
            (time(14, 0), time(15, 30)),
            (time(14, 30), time(16, 0)),
            (time(15, 0), time(16, 30)),
            (time(16, 0), time(17, 30)), # Late afternoon
            (time(16, 30), time(18, 0)),
            (time(17, 0), time(18, 30)),
            (time(18, 0), time(19, 30)), # Evening
            (time(18, 30), time(20, 0)),
            (time(19, 0), time(20, 30)),
            (time(20, 0), time(21, 30)), # Late evening
        ]
        
        group_counter = 1000
        
        for i in range(count):
            branch = random.choice(branches)
            branch_rooms = [r for r in rooms if r.branch == branch and r.is_active]
            branch_teachers = [t for t in teachers if hasattr(t, 'employee') and t.employee.branch == branch and t.employee.is_active]
            
            if not branch_rooms:
                continue
            
            start_time, end_time = random.choice(time_slots)
            course = random.choice(courses)
            
            # Generate realistic group name
            course_abbr = ''.join([word[0] for word in course.name.split()[:3]]).upper()
            group_name = f"{course_abbr}-{group_counter}"
            group_counter += 1
            
            # Capacity based on room capacity
            room = random.choice(branch_rooms)
            group_capacity = random.randint(
                max(5, room.capacity - 10),
                room.capacity
            )
            
            # Status distribution
            status = random.choices(
                ['active', 'completed', 'upcoming'],
                weights=[75, 15, 10]
            )[0]
            
            # Date based on status
            if status == 'completed':
                start_date = timezone.now().date() - timedelta(days=random.randint(90, 365))
            elif status == 'upcoming':
                start_date = timezone.now().date() + timedelta(days=random.randint(1, 60))
            else:  # active
                start_date = timezone.now().date() - timedelta(days=random.randint(1, 120))
            
            group = Group.objects.create(
                name=group_name,
                course=course,
                teacher=random.choice(branch_teachers) if branch_teachers else random.choice(teachers) if teachers else None,
                room=room,
                branch=branch,
                capacity=group_capacity,
                day_type=random.choice(day_types),
                status=status,
                start_time=start_time,
                end_time=end_time,
                start_date=start_date,
                notes=f'Created for {course.name}' if random.random() > 0.5 else ''
            )
            groups.append(group)
            
        return groups

    def assign_students_to_groups(self, students, groups):
        """Assign students to groups with realistic distribution"""
        active_groups = [g for g in groups if g.status == 'active']
        
        for student in students:
            if student.status == 'active' and active_groups:
                # Students more likely to join groups at their branch
                same_branch_groups = [g for g in active_groups if g.branch == student.branch and not g.is_full]
                other_groups = [g for g in active_groups if g.branch != student.branch and not g.is_full]
                
                available_groups = same_branch_groups if same_branch_groups else other_groups
                
                if available_groups:
                    # 80% chance of being in a group
                    if random.random() < 0.8:
                        group = random.choice(available_groups)
                        student.group = group
                        student.save()

    def create_leads(self, branches, courses, count):
        # Create pipeline stages first
        pipeline_stages_data = [
            ('New', 'New leads that just came in', 1, '#3b82f6'),  # Blue
            ('Contacted', 'Leads that have been contacted', 2, '#8b5cf6'),  # Purple
            ('First Trial', 'Leads who attended first trial lesson', 3, '#f59e0b'),  # Amber
            ('Success', 'Converted to students', 4, '#10b981'),  # Green
            ('Rejected', 'Leads that were rejected or not interested', 5, '#ef4444'),  # Red
        ]
        
        pipeline_stages = []
        for name, description, order, color in pipeline_stages_data:
            stage, created = PipelineStage.objects.get_or_create(
                name=name,
                defaults={
                    'description': description,
                    'order': order,
                    'color': color,
                    'is_active': True
                }
            )
            pipeline_stages.append(stage)
            if created:
                self.stdout.write(f'  → Created pipeline stage: {name}')
        
        # Get staff users for assignment
        staff_users = list(CustomUser.objects.filter(is_staff=True))
        
        first_names = [
            'Ahmed', 'Fatima', 'Akbar', 'Zebo', 'Rustam', 'Nilufar', 'Shavkat', 'Madina',
            'Omar', 'Aisha', 'Ali', 'Layla', 'Hassan', 'Zainab', 'Yusuf', 'Maryam',
            'Dmitry', 'Irina', 'Pavel', 'Ekaterina', 'Mikhail', 'Anastasia'
        ]
        last_names = [
            'Abdullayev', 'Karimova', 'Sadikov', 'Mirzayeva', 'Azimov', 'Usmanova',
            'Khan', 'Ahmed', 'Ali', 'Hussain', 'Rahman', 'Hassan',
            'Petrov', 'Ivanova', 'Smirnov', 'Kuznetsova'
        ]
        
        sources = ['website', 'instagram', 'facebook', 'telegram', 'referral', 'phone_call', 'walk_in', 'youtube']
        statuses = ['new', 'contacted', 'interested', 'not_interested', 'enrolled']
        
        # Distribute leads across pipeline stages: 40% new, 25% contacted, 20% first trial, 10% success, 5% rejected
        stage_distribution = [
            (pipeline_stages[0], 40),  # New
            (pipeline_stages[1], 25),  # Contacted
            (pipeline_stages[2], 20),  # First Trial
            (pipeline_stages[3], 10),  # Success
            (pipeline_stages[4], 5),   # Rejected
        ]
        
        leads = []
        for i in range(count):
            phone = f"+99893{random.randint(1000000, 9999999)}"
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            
            # Select pipeline stage based on distribution
            rand_val = random.randint(1, 100)
            cumulative = 0
            selected_stage = pipeline_stages[0]  # Default to New
            for stage, weight in stage_distribution:
                cumulative += weight
                if rand_val <= cumulative:
                    selected_stage = stage
                    break
            
            # Determine status based on pipeline stage
            if selected_stage.name == 'New':
                status = 'new'
            elif selected_stage.name == 'Contacted':
                status = 'contacted'
            elif selected_stage.name == 'First Trial':
                status = 'interested'
            elif selected_stage.name == 'Success':
                status = 'enrolled'
            else:  # Rejected
                status = 'not_interested'
            
            created_days_ago = random.randint(0, 90)
            
            lead = Lead.objects.create(
                full_name=f"{first_name} {last_name}",
                phone_number=phone,
                interested_course=random.choice(courses) if random.random() > 0.2 else None,
                pipeline_stage=selected_stage,
                status=status,
                source=random.choice(sources),
                branch=random.choice(branches),
                assigned_to=random.choice(staff_users) if staff_users and random.random() > 0.3 else None,
                preferred_time=random.choice(['Morning (8-12)', 'Afternoon (12-16)', 'Evening (16-20)', 'Flexible']),
                created_at=timezone.now() - timedelta(days=created_days_ago),
                notes=f'Contacted {random.randint(1, 5)} times' if status in ['contacted', 'interested'] else '',
                last_contacted=timezone.now() - timedelta(days=random.randint(0, 30)) if status in ['contacted', 'interested', 'enrolled'] else None,
                next_follow_up=timezone.now() + timedelta(days=random.randint(1, 14)) if status in ['contacted', 'interested'] else None,
                follow_up_count=random.randint(0, 8) if status in ['contacted', 'interested'] else 0,
            )
            leads.append(lead)
        
        return leads
        day_types = ['odd', 'even', 'daily']
        
        # Time slots for classes
        time_slots = [
            (time(9, 0), time(10, 30)),
            (time(11, 0), time(12, 30)),
            (time(14, 0), time(15, 30)),
            (time(16, 0), time(17, 30)),
            (time(18, 0), time(19, 30)),
        ]
        
        for i in range(count):
            branch = random.choice(branches)
            branch_rooms = [r for r in rooms if r.branch == branch]
            
            if not branch_rooms:
                continue
            
            start_time, end_time = random.choice(time_slots)
            
            group = Group.objects.create(
                name=f"RG-{1000 + i}",
                course=random.choice(courses),
                teacher=random.choice(teachers) if teachers else None,
                room=random.choice(branch_rooms),
                branch=branch,
                capacity=random.randint(10, 25),
                day_type=random.choice(day_types),
                status='active',
                start_time=start_time,
                end_time=end_time,
                start_date=timezone.now().date() - timedelta(days=random.randint(1, 90)),
            )
            groups.append(group)
        
        return groups

    def assign_students_to_groups(self, students, groups):
        """Randomly assign students to groups"""
        for student in students:
            if student.status == 'active' and groups:
                # Assign to a group with available capacity
                available_groups = [g for g in groups if not g.is_full]
                if available_groups:
                    group = random.choice(available_groups)
                    student.group = group
                    student.save()

    def create_attendance_data(self, groups):
        """Generate Attendance records for past sessions and AttendanceReport summaries."""
        from datetime import date as _date

        DAY_MAP = {
            'odd':   {0, 2, 4},
            'even':  {1, 3, 5},
            'daily': {0, 1, 2, 3, 4, 5},
        }
        STATUS_WEIGHTS = ['present', 'present', 'present', 'present', 'present',
                          'absent', 'late', 'excused']

        today = _date.today()
        total_att = 0
        total_reports = 0

        for group in groups:
            if not group.start_date or group.start_date > today:
                continue

            weekdays = DAY_MAP.get(group.day_type, {0, 2, 4})
            end = min(group.end_date, today) if group.end_date else today

            # Collect past class dates (skip weekends outside schedule)
            past_dates = []
            cur = group.start_date
            while cur <= end:
                if cur.weekday() in weekdays:
                    past_dates.append(cur)
                cur += timedelta(days=1)

            if not past_dates:
                continue

            students = list(group.students.filter(status='active').select_related('user'))
            if not students:
                continue

            # Bulk-create attendance records
            to_create = []
            for d in past_dates:
                for student in students:
                    to_create.append(Attendance(
                        student=student,
                        group=group,
                        date=d,
                        status=random.choice(STATUS_WEIGHTS),
                    ))

            created = Attendance.objects.bulk_create(to_create, ignore_conflicts=True)
            total_att += len(created)

            # Build AttendanceReport for this group
            all_att = Attendance.objects.filter(group=group, date__in=past_dates)
            total_classes = len(past_dates)
            present_count = all_att.filter(status='present').count()
            absent_count  = all_att.filter(status='absent').count()
            late_count    = all_att.filter(status='late').count()
            excused_count = all_att.filter(status='excused').count()
            total_records = all_att.count()
            rate = round((present_count / total_records * 100), 2) if total_records else 0

            AttendanceReport.objects.update_or_create(
                report_type='group',
                group=group,
                start_date=group.start_date,
                end_date=today,
                defaults={
                    'total_classes': total_classes,
                    'present_count': present_count,
                    'absent_count': absent_count,
                    'late_count': late_count,
                    'excused_count': excused_count,
                    'attendance_rate': rate,
                }
            )
            total_reports += 1

        return total_att, total_reports
