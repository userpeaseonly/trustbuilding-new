from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from courses.models import Course
from dashboard.models import DashboardSettings
from employees.models import Employee, Permission, Role
from groups.models import Group, Room
from users.models import Branch, CustomUser


class DashboardScheduleTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            phone_number='+998900000001',
            password='pass12345',
            full_name='Admin',
        )
        self.teacher = CustomUser.objects.create_user(
            phone_number='+998900000002',
            password='pass12345',
            full_name='Teacher',
            is_teacher=True,
        )
        self.branch = Branch.objects.create(name='Main', short_name='MN')
        self.other_branch = Branch.objects.create(name='Other', short_name='OT')
        self.role = Role.objects.create(name='Dashboard Viewer')
        Permission.objects.create(
            role=self.role,
            app='dashboard',
            feature='view',
            feature_display='Dashboard View',
            can_view=True,
        )
        self.course = Course.objects.create(
            name='English',
            total_lessons=12,
            lessons_per_week=3,
            color='#16a34a',
        )
        DashboardSettings.objects.update_or_create(
            pk=1,
            defaults={
                'schedule_start_time': time(9, 0),
                'schedule_end_time': time(13, 0),
                'time_slot_minutes': 30,
            },
        )

    def _group(self, name, room, start, end, *, branch=None):
        return Group.objects.create(
            name=name,
            course=self.course,
            teacher=self.teacher,
            room=room,
            branch=branch or room.branch,
            day_type='odd',
            status='active',
            start_time=start,
            end_time=end,
            start_date=date(2026, 6, 1),
        )

    def test_room_schedule_shows_group_when_start_time_is_inside_slot(self):
        room = Room.objects.create(name='101', branch=self.branch, is_active=True)
        target_group = self._group('RG-INSIDE-SLOT', room, time(9, 10), time(10, 40))
        self._group('RG-SAME-TEACHER-LATER', room, time(11, 0), time(12, 30))

        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard:home'), {
            'view_by': 'group',
            'day_type': 'daily',
        })

        self.assertEqual(response.status_code, 200)
        schedule_grid = response.context['schedule_grid']
        room_column = next(column for column in response.context['columns'] if column.id == room.id)
        rendered_group = schedule_grid['09:00 - 09:30'][room_column.schedule_key]
        self.assertEqual(rendered_group, target_group)
        self.assertEqual(rendered_group.rowspan, 4)

    def test_room_schedule_uses_stable_column_keys_for_duplicate_room_names(self):
        main_room = Room.objects.create(name='101', branch=self.branch, is_active=True)
        other_room = Room.objects.create(name='101', branch=self.other_branch, is_active=True)
        main_group = self._group('RG-MAIN-BRANCH', main_room, time(9, 0), time(10, 30))
        other_group = self._group('RG-OTHER-BRANCH', other_room, time(9, 0), time(10, 30))

        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard:home'), {
            'view_by': 'group',
            'day_type': 'daily',
        })

        self.assertEqual(response.status_code, 200)
        schedule_grid = response.context['schedule_grid']
        columns_by_room_id = {column.id: column for column in response.context['columns']}
        self.assertEqual(
            schedule_grid['09:00 - 09:30'][columns_by_room_id[main_room.id].schedule_key],
            main_group,
        )
        self.assertEqual(
            schedule_grid['09:00 - 09:30'][columns_by_room_id[other_room.id].schedule_key],
            other_group,
        )
        self.assertEqual(columns_by_room_id[main_room.id].schedule_label, '101-MN')
        self.assertEqual(columns_by_room_id[other_room.id].schedule_label, '101-OT')

    def test_branch_scoped_room_schedule_keeps_plain_room_names(self):
        room = Room.objects.create(name='101', branch=self.branch, is_active=True)
        other_room = Room.objects.create(name='101', branch=self.other_branch, is_active=True)
        self._group('RG-MAIN-BRANCH', room, time(9, 0), time(10, 30))
        self._group('RG-OTHER-BRANCH', other_room, time(9, 0), time(10, 30))
        branch_user = CustomUser.objects.create_user(
            phone_number='+998900000003',
            password='pass12345',
            full_name='Branch User',
        )
        Employee.objects.create(
            user=branch_user,
            role=self.role,
            branch=self.branch,
            position='manager',
            hire_date=date(2026, 1, 1),
            is_active=True,
        )

        self.client.force_login(branch_user)
        response = self.client.get(reverse('dashboard:home'), {
            'view_by': 'group',
            'day_type': 'daily',
        })

        self.assertEqual(response.status_code, 200)
        columns = list(response.context['columns'])
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0].id, room.id)
        self.assertEqual(columns[0].schedule_label, '101')

    def test_room_schedule_does_not_render_group_under_room_from_different_branch(self):
        main_room = Room.objects.create(name='101', branch=self.branch, is_active=True)
        mismatched_group = self._group(
            'OG-1002',
            main_room,
            time(9, 0),
            time(10, 30),
            branch=self.other_branch,
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard:home'), {
            'view_by': 'group',
            'day_type': 'daily',
        })

        self.assertEqual(response.status_code, 200)
        schedule_grid = response.context['schedule_grid']
        room_column = next(column for column in response.context['columns'] if column.id == main_room.id)
        self.assertIsNone(schedule_grid['09:00 - 09:30'][room_column.schedule_key])
        self.assertEqual(mismatched_group.branch, self.other_branch)
        self.assertEqual(mismatched_group.room.branch, self.branch)

    def test_superuser_can_filter_dashboard_by_branch(self):
        main_room = Room.objects.create(name='101', branch=self.branch, is_active=True)
        other_room = Room.objects.create(name='101', branch=self.other_branch, is_active=True)
        self._group('RG-1001', main_room, time(9, 0), time(10, 30))
        other_group = self._group('OG-1001', other_room, time(9, 0), time(10, 30))

        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard:home'), {
            'view_by': 'group',
            'day_type': 'daily',
            'branch': self.other_branch.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_branch'], self.other_branch)
        self.assertEqual(response.context['stats']['active_groups'], 1)
        columns = list(response.context['columns'])
        self.assertEqual([column.id for column in columns], [other_room.id])
        schedule_grid = response.context['schedule_grid']
        self.assertEqual(schedule_grid['09:00 - 09:30'][columns[0].schedule_key], other_group)

    def test_branch_filter_htmx_request_refreshes_dashboard_content(self):
        Room.objects.create(name='101', branch=self.other_branch, is_active=True)

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('dashboard:home'),
            {
                'view_by': 'group',
                'day_type': 'daily',
                'branch': self.other_branch.pk,
            },
            HTTP_HX_REQUEST='true',
            HTTP_HX_TARGET='main-content',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/partials/home_content.html')
        self.assertContains(response, 'name="branch"')
