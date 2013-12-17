
# vim: set fileencoding=utf-8 :

# Beaker
#
# Copyright (C) 2010 dcallagh@redhat.com
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import unittest
import logging
import time
import re
import tempfile
import pkg_resources
from turbogears.database import session
from selenium.webdriver.support.ui import Select
from bkr.inttest.server.selenium import SeleniumTestCase, WebDriverTestCase
from bkr.inttest.server.webdriver_utils import login, is_text_present, logout
from bkr.inttest import data_setup, with_transaction, get_server_base
from bkr.server.model import RetentionTag, Product, Distro, Job, GuestRecipe, \
    User

class TestViewJob(WebDriverTestCase):

    def setUp(self):
        self.browser = self.get_browser()

    def tearDown(self):
        self.browser.quit()

    def test_group_job(self):
        with session.begin():
            user = data_setup.create_user()
            group = data_setup.create_group()
            job = data_setup.create_job(group=group)
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        b.find_element_by_link_text("%s" % job.group).click()
        b.find_element_by_xpath('//h1[text()="%s"]' % group.display_name)

    def test_cc_list(self):
        with session.begin():
            user = data_setup.create_user(password=u'password')
            job = data_setup.create_job(owner=user,
                    cc=[u'laika@mir.su', u'tereshkova@kosmonavt.su'])
        b = self.browser
        login(b, user=user.user_name, password='password')
        b.get(get_server_base())
        b.find_element_by_link_text('My Jobs').click()
        b.find_element_by_link_text(job.t_id).click()
        b.find_element_by_xpath('//td[.//text()="%s"]' % job.t_id)
        self.assertEqual(
            # value of cell beside "CC" cell
            b.find_element_by_xpath('//table//td'
                '[preceding-sibling::th[1]/text() = "CC"]').text,
            'laika@mir.su; tereshkova@kosmonavt.su')

    def test_edit_job_whiteboard(self):
        with session.begin():
            user = data_setup.create_user(password=u'asdf')
            job = data_setup.create_job(owner=user)
        b = self.browser
        login(b, user=user.user_name, password='asdf')
        b.get(get_server_base() + 'jobs/%s' % job.id)
        new_whiteboard = 'new whiteboard value %s' % int(time.time())
        b.find_element_by_xpath(
                '//td[preceding-sibling::th[1]/text()="Whiteboard"]'
                '//a[text()="(Edit)"]').click()
        b.find_element_by_name('whiteboard').clear()
        b.find_element_by_name('whiteboard').send_keys(new_whiteboard)
        b.find_element_by_xpath('//form[@id="job_whiteboard_form"]'
                '//button[@type="submit"]').click()
        b.find_element_by_xpath(
                '//form[@id="job_whiteboard_form"]//div[@class="msg success"]')
        b.get(get_server_base() + 'jobs/%s' % job.id)
        b.find_element_by_xpath('//input[@name="whiteboard" and @value="%s"]'
                % new_whiteboard)

    def test_datetimes_are_localised(self):
        with session.begin():
            job = data_setup.create_completed_job()
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        self.check_datetime_localised(b.find_element_by_xpath(
                '//table//td'
                '[preceding-sibling::th[1]/text() = "Queued"]').text)
        self.check_datetime_localised(b.find_element_by_xpath(
                '//table//td'
                '[preceding-sibling::th[1]/text() = "Started"]').text)
        self.check_datetime_localised(b.find_element_by_xpath(
                '//table//td'
                '[preceding-sibling::th[1]/text() = "Finished"]').text)

    def test_invalid_datetimes_arent_localised(self):
        with session.begin():
            job = data_setup.create_job()
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        self.assertEquals(
                b.find_element_by_xpath('//table//td'
                '[preceding-sibling::th[1]/text() = "Finished"]').text,
                '')

    # https://bugzilla.redhat.com/show_bug.cgi?id=706435
    def test_task_result_datetimes_are_localised(self):
        with session.begin():
            job = data_setup.create_completed_job()
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        recipe_id = job.recipesets[0].recipes[0].id
        b.find_element_by_xpath('//div[@id="recipe%s"]//a[text()="Show Results"]' % recipe_id).click()
        b.find_element_by_xpath(
                '//div[@id="recipe-%d-results"]//table' % recipe_id)
        recipe_task_start, recipe_task_finish = \
                b.find_elements_by_xpath(
                    '//div[@id="recipe-%d-results"]//table'
                    '/tbody/tr[1]/td[3]/span' % recipe_id)
        self.check_datetime_localised(recipe_task_start.text.strip())
        self.check_datetime_localised(recipe_task_finish.text.strip())
        self.check_datetime_localised(b.find_element_by_xpath(
                '//div[@id="recipe-%d-results"]//table'
                '/tbody/tr[2]/td[3]' % recipe_id).text)

    def check_datetime_localised(self, dt):
        self.assert_(re.match(r'\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d [-+]\d\d:\d\d$', dt),
                '%r does not look like a localised datetime' % dt)

    # https://bugzilla.redhat.com/show_bug.cgi?id=881387
    def test_guestrecipes_appear_after_host(self):
        with session.begin():
            # hack to force the GuestRecipe to be inserted first
            guest = data_setup.create_recipe(cls=GuestRecipe)
            job = data_setup.create_job_for_recipes([guest])
            session.flush()
            host = data_setup.create_recipe()
            job.recipesets[0].recipes.append(host)
            host.guests.append(guest)
            session.flush()
            self.assert_(guest.id < host.id)
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        recipe_order = [elem.text for elem in b.find_elements_by_xpath(
                '//a[@class="recipe-id"]')]
        self.assertEquals(recipe_order, [host.t_id, guest.t_id])

class NewJobTestWD(WebDriverTestCase):

    def setUp(self):
        self.browser = self.get_browser()
        with session.begin():
            self.user = data_setup.create_user(password=u'password')
            if not Distro.by_name(u'BlueShoeLinux5-5'):
                data_setup.create_distro_tree(distro_name=u'BlueShoeLinux5-5')
            data_setup.create_product(product_name=u'the_product')

    def tearDown(self):
        self.browser.quit()

    # https://bugzilla.redhat.com/show_bug.cgi?id=949777
    def test_invalid_inventory_date_with_equal(self):

        b = self.browser
        login(b, user=self.user.user_name, password='password')
        b.get(get_server_base() + 'jobs/new')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with invalid date value with equal op</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires>
                           <system>
                              <last_inventoried op="=" value="2010-10-10 10:10:10"/>
                           </system>
                           <system_type value="Machine"/>
                        </hostRequires>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        b.find_element_by_xpath("//input[@id='jobs_filexml']").send_keys(xml_file.name)
        b.find_element_by_xpath("//button[text()='Submit Data']").click()
        b.find_element_by_xpath("//button[text()='Queue']").click()
        b.find_element_by_xpath('//div[contains(@class, "alert")]'
                '/h4[contains(text(), "Job failed schema validation")]')

    # https://bugzilla.redhat.com/show_bug.cgi?id=949777
    def test_invalid_inventory_date_with_not_equal(self):

        b = self.browser
        login(b, user=self.user.user_name, password='password')
        b.get(get_server_base() + 'jobs/new')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with invalid date value with equal op</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires>
                           <system>
                              <last_inventoried op="!=" value="2010-10-10 10:10:10"/>
                           </system>
                           <system_type value="Machine"/>
                        </hostRequires>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        b.find_element_by_xpath("//input[@id='jobs_filexml']").send_keys(xml_file.name)
        b.find_element_by_xpath("//button[text()='Submit Data']").click()
        b.find_element_by_xpath("//button[text()='Queue']").click()
        b.find_element_by_xpath('//div[contains(@class, "alert")]'
                '/h4[contains(text(), "Job failed schema validation")]')

    def test_valid_submission_delegate(self):
        with session.begin():
            user = data_setup.create_user()
            submission_delegate = data_setup.create_user(password='password')
            user.submission_delegates[:] = [submission_delegate]

        b = self.browser
        login(b, user=submission_delegate.user_name, password='password')
        b.get(get_server_base() + 'jobs/new')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job user="%s">
                <whiteboard>job with submission delegate who is allowed</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires>
                           <system_type value="Machine"/>
                        </hostRequires>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''' % user.user_name)
        xml_file.flush()
        b.find_element_by_xpath("//input[@id='jobs_filexml']").send_keys(xml_file.name)
        b.find_element_by_xpath("//button[text()='Submit Data']").click()
        b.find_element_by_xpath("//button[text()='Queue']").click()
        flash_text = b.find_element_by_class_name('flash').text
        self.assert_('Success!' in flash_text, flash_text)
        self.assertEqual(b.title, 'My Jobs')

    def test_invalid_submission_delegate(self):
        with session.begin():
            user = data_setup.create_user()
            invalid_delegate = data_setup.create_user(password='password')

        b = self.browser
        login(b, user=invalid_delegate.user_name, password='password')
        b.get(get_server_base() + 'jobs/new')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job user="%s">
                <whiteboard>job with submission delegate who is not allowed</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires>
                           <system>
                              <last_inventoried op="&gt;" value="2010-10-10"/>
                           </system>
                           <system_type value="Machine"/>
                        </hostRequires>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''' % user.user_name)
        xml_file.flush()
        b.find_element_by_xpath("//input[@id='jobs_filexml']").send_keys(xml_file.name)
        b.find_element_by_xpath("//button[text()='Submit Data']").click()
        b.find_element_by_xpath("//button[text()='Queue']").click()
        flash_text = b.find_element_by_class_name('flash').text
        self.assertEquals('Failed to import job because of: %s is not a valid'
            ' submission delegate for %s' % (invalid_delegate.user_name, user.user_name), flash_text, flash_text)

    # https://bugzilla.redhat.com/show_bug.cgi?id=949777
    def test_valid_inventory_date(self):

        b = self.browser
        login(b, user=self.user.user_name, password='password')
        b.get(get_server_base() + 'jobs/new')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with invalid date value with equal op</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires>
                           <system>
                              <last_inventoried op="&gt;" value="2010-10-10"/>
                           </system>
                           <system_type value="Machine"/>
                        </hostRequires>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        b.find_element_by_xpath("//input[@id='jobs_filexml']").send_keys(xml_file.name)
        b.find_element_by_xpath("//button[text()='Submit Data']").click()
        b.find_element_by_xpath("//button[text()='Queue']").click()
        flash_text = b.find_element_by_class_name('flash').text
        self.assert_('Success!' in flash_text, flash_text)
        self.assertEqual(b.title, 'My Jobs')

    # https://bugzilla.redhat.com/show_bug.cgi?id=972412
    def test_invalid_utf8_chars(self):
        b = self.browser
        login(b, user=self.user.user_name, password='password')
        b.get(get_server_base() + 'jobs/new')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('\x89')
        xml_file.flush()
        b.find_element_by_xpath("//input[@id='jobs_filexml']").send_keys(xml_file.name)
        b.find_element_by_xpath("//button[text()='Submit Data']").click()
        flash_text = b.find_element_by_class_name('flash').text
        self.assertEquals(flash_text,
                "Invalid job XML: 'utf8' codec can't decode byte 0x89 "
                "in position 0: invalid start byte")

class NewJobTest(SeleniumTestCase):

    @with_transaction
    def setUp(self):
        if not Distro.by_name(u'BlueShoeLinux5-5'):
            data_setup.create_distro_tree(distro_name=u'BlueShoeLinux5-5')
        data_setup.create_product(product_name=u'the_product')
        self.selenium = self.get_selenium()
        self.selenium.start()

    def tearDown(self):
        self.selenium.stop()

    def test_warns_about_xsd_validation_errors(self):
        self.login()
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with invalid hostRequires</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires/>
                        <task name="/distribution/install" role="STANDALONE">
                            <params/>
                        </task>
                        <brokenElement/>
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        self.assertEqual(sel.get_text('css=.alert-error h4'),
                'Job failed schema validation. Please confirm that you want to submit it.')
        self.assert_(int(sel.get_xpath_count('//ul[@class="xsd-error-list"]/li')) > 0)
        sel.click('//button[text()="Queue despite validation errors"]')
        sel.wait_for_page_to_load('30000')
        self.assertEqual(sel.get_title(), 'My Jobs')
        self.assert_(sel.get_text('css=.flash').startswith('Success!'))

    def test_refuses_to_accept_unparseable_xml(self):
        self.login()
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with unterminated whiteboard
            </job>
            ''')
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        self.assert_('Failed to import job' in sel.get_text('css=.flash'))

    def test_valid_job_xml_doesnt_trigger_xsd_warning(self):
        with session.begin():
            group = data_setup.create_group(group_name='somegroup')
            user = data_setup.create_user(password=u'hornet')
            user.groups.append(group)

        self.login(user=user.user_name, password='hornet')
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        sel.type('jobs_filexml', pkg_resources.resource_filename(
                'bkr.inttest', 'complete-job.xml'))
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        self.assertEqual(sel.get_title(), 'My Jobs')
        self.assert_(sel.get_text('css=.flash').startswith('Success!'))

    # https://bugzilla.redhat.com/show_bug.cgi?id=661652
    def test_job_with_excluded_task(self):
        with session.begin():
            distro_tree = data_setup.create_distro_tree(arch=u'ia64')
            excluded_task = data_setup.create_task(exclude_arch=[u'ia64'])
        self.login()
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with excluded task</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="%s" />
                            <distro_arch op="=" value="ia64" />
                        </distroRequires>
                        <hostRequires/>
                        <task name="/distribution/install" role="STANDALONE">
                            <params/>
                        </task>
                        <task name="%s" role="STANDALONE">
                            <params/>
                        </task>
                    </recipe>
                </recipeSet>
            </job>
            ''' % (distro_tree.distro.name, excluded_task.name))
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        flash = sel.get_text('css=.flash')
        self.assert_(flash.startswith('Success!'), flash)
        self.assertEqual(sel.get_title(), 'My Jobs')

    # https://bugzilla.redhat.com/show_bug.cgi?id=689344
    def test_partition_without_fs_doesnt_trigger_validation_warning(self):
        self.login()
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with partition without fs</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires/>
                        <partitions>
                            <partition name="/" size="4" type="part"/>
                        </partitions>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        flash = sel.get_text('css=.flash')
        self.assert_(flash.startswith('Success!'), flash)
        self.assertEqual(sel.get_title(), 'My Jobs')

    # https://bugzilla.redhat.com/show_bug.cgi?id=730983
    def test_duplicate_notify_cc_addresses_are_merged(self):
        with session.begin():
            user = data_setup.create_user(password=u'hornet')
        self.login(user.user_name, u'hornet')
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with duplicate notify cc addresses</whiteboard>
                <notify>
                    <cc>person@example.invalid</cc>
                    <cc>person@example.invalid</cc>
                </notify>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires/>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        flash = sel.get_text('css=.flash')
        self.assert_(flash.startswith('Success!'), flash)
        self.assertEqual(sel.get_title(), 'My Jobs')
        job = Job.query.filter(Job.owner == user).order_by(Job.id.desc()).first()
        self.assertEqual(job.cc, ['person@example.invalid'])

    # https://bugzilla.redhat.com/show_bug.cgi?id=784237
    def test_invalid_email_addresses_are_not_accepted_in_notify_cc(self):
        self.login()
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with invalid notify cc addresses</whiteboard>
                <notify>
                    <cc>asdf</cc>
                </notify>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires/>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        self.assert_('Failed to import job' in sel.get_text('css=.flash'))

    # https://bugzilla.redhat.com/show_bug.cgi?id=741170
    # You will need a patched python-xmltramp for this test to pass.
    # Look for python-xmltramp-2.17-8.eso.1 or higher.
    def test_doesnt_barf_on_xmlns(self):
        self.login()
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''
            <job>
                <whiteboard>job with namespace prefix declaration</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires xmlns:str="http://exslt.org/strings">
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires/>
                        <task name="/distribution/install" role="STANDALONE"/>
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        flash = sel.get_text('css=.flash')
        self.assert_(flash.startswith('Success!'), flash)
        self.assertEqual(sel.get_title(), 'My Jobs')

    # https://bugzilla.redhat.com/show_bug.cgi?id=768167
    def test_doesnt_barf_on_xml_encoding_declaration(self):
        self.login()
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        xml_file.write('''<?xml version="1.0" encoding="utf-8"?>
            <job>
                <whiteboard>job with encoding in XML declaration яяя</whiteboard>
                <recipeSet>
                    <recipe>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires/>
                        <task name="/distribution/install" />
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        flash = sel.get_text('css=.flash')
        self.assert_(flash.startswith('Success!'), flash)
        self.assertEqual(sel.get_title(), 'My Jobs')

    # https://bugzilla.redhat.com/show_bug.cgi?id=869455
    # https://bugzilla.redhat.com/show_bug.cgi?id=896622
    def test_recipe_not_added_to_session_too_early(self):
        self.login()
        sel = self.selenium
        sel.open('')
        sel.click('link=New Job')
        sel.wait_for_page_to_load('30000')
        xml_file = tempfile.NamedTemporaryFile()
        # These bugs are triggered by related entites of Recipe (ks_appends, 
        # repos, and packages) pulling the recipe into the session too early. 
        # So our test job XML has one of each on the recipe and its 
        # guestrecipe, to cover all cases.
        xml_file.write('''<?xml version="1.0" encoding="utf-8"?>
            <job>
                <whiteboard>job with package</whiteboard>
                <recipeSet>
                    <recipe>
                        <guestrecipe guestargs="--kvm" guestname="one">
                            <ks_appends>
                                <ks_append>append1</ks_append>
                            </ks_appends>
                            <packages>
                                <package name="package1" />
                            </packages>
                            <repos>
                                <repo name="repo1" url="http://example.com/" />
                            </repos>
                            <distroRequires>
                                <distro_name op="=" value="BlueShoeLinux5-5" />
                            </distroRequires>
                            <hostRequires/>
                            <task name="/distribution/install" />
                        </guestrecipe>
                        <ks_appends>
                            <ks_append>append2</ks_append>
                        </ks_appends>
                        <packages>
                            <package name="package2" />
                        </packages>
                        <repos>
                            <repo name="repo2" url="http://example.com/" />
                        </repos>
                        <distroRequires>
                            <distro_name op="=" value="BlueShoeLinux5-5" />
                        </distroRequires>
                        <hostRequires/>
                        <task name="/distribution/install" />
                    </recipe>
                </recipeSet>
            </job>
            ''')
        xml_file.flush()
        sel.type('jobs_filexml', xml_file.name)
        sel.click('//button[text()="Submit Data"]')
        sel.wait_for_page_to_load('30000')
        sel.click('//button[text()="Queue"]')
        sel.wait_for_page_to_load('30000')
        flash = sel.get_text('css=.flash')
        self.assert_(flash.startswith('Success!'), flash)
        self.assertEqual(sel.get_title(), 'My Jobs')


class JobAttributeChangeTest(WebDriverTestCase):

    def setUp(self):
        self.browser = self.get_browser()

    def tearDown(self):
        self.browser.quit()

    def check_can_change_product(self, job, new_product):
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        Select(b.find_element_by_id('job_product'))\
            .select_by_visible_text(new_product.name)
        b.find_element_by_xpath('//div[text()="Product has been updated"]')

    def check_cannot_change_product(self, job):
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        self.assertFalse(b.find_element_by_id('job_product').is_enabled())

    def check_can_change_retention_tag(self, job, new_tag):
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        Select(b.find_element_by_id('job_retentiontag'))\
            .select_by_visible_text(new_tag)
        b.find_element_by_xpath('//div[text()="Tag has been updated"]')

    def check_cannot_change_retention_tag(self, job):
        b = self.browser
        b.get(get_server_base() + 'jobs/%s' % job.id)
        self.assertFalse(b.find_element_by_id('job_retentiontag').is_enabled())

    def test_job_owner_can_change_product(self):
        with session.begin():
            job_owner = data_setup.create_user(password=u'owner')
            job = data_setup.create_job(owner=job_owner,
                    retention_tag=u'active',
                    product=data_setup.create_product())
            new_product = data_setup.create_product()
        login(self.browser, user=job_owner.user_name, password=u'owner')
        self.check_can_change_product(job, new_product)

    def test_group_member_can_change_product(self):
        with session.begin():
            group = data_setup.create_group()
            job_owner = data_setup.create_user()
            group_member = data_setup.create_user(password=u'group_member')
            data_setup.add_user_to_group(job_owner, group)
            data_setup.add_user_to_group(group_member, group)
            job = data_setup.create_job(owner=job_owner,
                    retention_tag=u'active',
                    product=data_setup.create_product())
            new_product = data_setup.create_product()
        login(self.browser, user=group_member.user_name, password=u'group_member')
        self.check_can_change_product(job, new_product)

    def test_other_user_cannot_change_product(self):
        with session.begin():
            other_user = data_setup.create_user(password=u'other_user')
            job = data_setup.create_job(retention_tag=u'active',
                    product=data_setup.create_product())
        login(self.browser, user=other_user.user_name, password=u'other_user')
        self.check_cannot_change_product(job)

    def test_job_owner_can_change_retention_tag(self):
        with session.begin():
            job_owner = data_setup.create_user(password=u'owner')
            job = data_setup.create_job(owner=job_owner,
                    retention_tag=u'scratch')
        login(self.browser, user=job_owner.user_name, password=u'owner')
        self.check_can_change_retention_tag(job, '60days')

    def test_group_member_can_change_retention_tag(self):
        with session.begin():
            group = data_setup.create_group()
            job_owner = data_setup.create_user()
            group_member = data_setup.create_user(password=u'group_member')
            data_setup.add_user_to_group(job_owner, group)
            data_setup.add_user_to_group(group_member, group)
            job = data_setup.create_job(owner=job_owner,
                    retention_tag=u'scratch')
        login(self.browser, user=group_member.user_name, password=u'group_member')
        self.check_can_change_retention_tag(job, '60days')

    def test_other_user_cannot_change_retention_tag(self):
        with session.begin():
            other_user = data_setup.create_user(password=u'other_user')
            job = data_setup.create_job(retention_tag=u'scratch')
        login(self.browser, user=other_user.user_name, password=u'other_user')
        self.check_cannot_change_retention_tag(job)

class CloneJobTest(SeleniumTestCase):

    def setUp(self):
        self.selenium = self.get_selenium()
        self.selenium.start()

    def tearDown(self):
        self.selenium.stop()

    def test_cloning_recipeset_from_job_with_product(self):
        with session.begin():
            job = data_setup.create_job()
            job.retention_tag = RetentionTag.list_by_requires_product()[0]
            job.product = Product(u'product_name')
        self.login()
        sel =  self.selenium
        sel.open('jobs/clone?job_id=%s' % job.id)
        sel.wait_for_page_to_load('30000')
        cloned_from_job = sel.get_text('//textarea[@name="textxml"]')
        sel.open('jobs/clone?recipeset_id=%s' % job.recipesets[0].id)
        sel.wait_for_page_to_load('30000')
        cloned_from_rs = sel.get_text('//textarea[@name="textxml"]')
        self.assertEqual(cloned_from_job,cloned_from_rs)

    def test_cloning_recipeset(self):
        with session.begin():
            job = data_setup.create_job()
        self.login()
        sel = self.selenium
        sel.open('jobs/clone?job_id=%s' % job.id)
        sel.wait_for_page_to_load('30000')
        cloned_from_job = sel.get_text('//textarea[@name="textxml"]')
        sel.open('jobs/clone?recipeset_id=%s' % job.recipesets[0].id)
        sel.wait_for_page_to_load('30000')
        cloned_from_rs = sel.get_text('//textarea[@name="textxml"]')
        self.assertEqual(cloned_from_job, cloned_from_rs)

class TestJobsGrid(WebDriverTestCase):

    def setUp(self):
        self.browser = self.get_browser()

    def tearDown(self):
        self.browser.quit()

    def check_job_row(self, rownum, job_t_id, group):
        b = self.browser
        job_id = b.find_element_by_xpath('//table[@id="widget"]/tbody/tr[%d]/td[1]' % rownum).text
        group_name = b.find_element_by_xpath('//table[@id="widget"]/tbody/tr[%d]/td[3]' % rownum).text
        self.assertEquals(job_id, job_t_id)
        if group:
            self.assertEquals(group_name, group.group_name)
        else:
            self.assertEquals(group_name, "")

    def test_myjobs_group(self):
        with session.begin():
            user = data_setup.create_user(password='password')
            user2 = data_setup.create_user(password='password')
            group = data_setup.create_group()
            user.groups.append(group)
            user2.groups.append(group)
            job = data_setup.create_job(owner=user, group=group)
        b = self.browser
        login(b, user=user2.user_name, password='password')
        b.get(get_server_base() + 'jobs/mygroups')
        b.find_element_by_xpath('//title[normalize-space(text())="My Group Jobs"]')
        self.assertTrue(is_text_present(b, job.t_id))
        logout(b)
        login(b, user=user.user_name, password='password')
        b.get(get_server_base() + 'jobs/mygroups')
        b.find_element_by_xpath('//title[normalize-space(text())="My Group Jobs"]')
        self.assertTrue(is_text_present(b, job.t_id))

    def test_myjobs_individual(self):
        with session.begin():
            user = data_setup.create_user(password='password')
            job = data_setup.create_job(owner=user, group=None)
        b = self.browser
        login(b, user=user.user_name, password='password')
        b.find_element_by_link_text('My Jobs').click()
        b.find_element_by_xpath('//title[normalize-space(text())="My Jobs"]')
        self.assertTrue(is_text_present(b, job.t_id))

    def test_myjobs_submission_delegate(self):
        with session.begin():
            user = data_setup.create_user()
            submission_delegate = data_setup.create_user(password='password')
            user.submission_delegates[:] = [submission_delegate]
            job = data_setup.create_job(owner=user, group=None, submitter=submission_delegate)
        b = self.browser
        login(b, user=submission_delegate.user_name, password='password')
        b.find_element_by_link_text('My Jobs').click()
        b.find_element_by_xpath('//title[normalize-space(text())="My Jobs"]')
        self.assertTrue(is_text_present(b, job.t_id))

    def test_jobs_group_column(self):
        with session.begin():
            user = data_setup.create_user(password='password')
            group1 = data_setup.create_group(owner=user)
            group2 = data_setup.create_group()
            user.groups.append(group2)
            job1 = data_setup.create_job(owner=user, group=None)
            job2 = data_setup.create_job(owner=user, group=group1)
            job3 = data_setup.create_job(owner=user, group=group2)

        b = self.browser

        # jobs/mine
        login(b, user=user.user_name, password='password')
        b.find_element_by_link_text('My Jobs').click()
        b.find_element_by_xpath('//title[normalize-space(text())="My Jobs"]')

        self.check_job_row(rownum=1, job_t_id=job3.t_id, group=group2)
        self.check_job_row(rownum=2, job_t_id=job2.t_id, group=group1)
        self.check_job_row(rownum=3, job_t_id=job1.t_id, group=None)

        # jobs
        logout(b)
        b.get(get_server_base() + 'jobs/')
        self.check_job_row(rownum=1, job_t_id=job3.t_id, group=group2)
        self.check_job_row(rownum=2, job_t_id=job2.t_id, group=group1)
        self.check_job_row(rownum=3, job_t_id=job1.t_id, group=None)
