-- seat_members.sql — the first mei.members rows. Run ONCE in Supabase → SQL Editor after the mei migration is applied.
-- The login accounts must already exist in Authentication → Users (the same Supabase project as Rakusalab, so a
-- Rakusalab login can be reused as is). Replace the three e-mails; delete the lines you do not need.
with g as (
  insert into mei.gardens (name_ja) values ('関東の名園') returning id
),
people (email, role, name) as (
  values ('<your-login-email>',     'admin',    '管理者'),
         ('<supplier-login-email>', 'supplier', '園主'),
         ('<staff-login-email>',    'staff',    '工作人员')
)
insert into mei.members (user_id, role, garden_id, name)
select u.id, p.role::mei.member_role, case when p.role = 'supplier' then g.id end, p.name
from people p
join auth.users u on lower(u.email) = lower(p.email)
cross join g
on conflict (user_id) do update set role = excluded.role, garden_id = excluded.garden_id, name = excluded.name, active = true;

-- check: three rows, the supplier with a garden
select m.role, m.name, u.email, m.garden_id from mei.members m join auth.users u on u.id = m.user_id;
