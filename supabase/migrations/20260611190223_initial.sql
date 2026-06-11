-- Hope Server Monitor — Esquema Supabase
-- Ejecutar en SQL Editor del dashboard de Supabase

-- 1. Servidores
create table if not exists servers (
  id text primary key,
  owner_id uuid not null,
  name text not null,
  target text not null,
  type text default 'server',
  status text default 'unknown',
  last_checked timestamptz,
  created_at timestamptz default now(),
  shock_config text default ''
);

-- 2. Cambios
create table if not exists server_changes (
  id text primary key,
  server_id text references servers(id) on delete cascade,
  title text not null,
  description text default '',
  severity text default 'medium',
  timestamp timestamptz default now()
);

-- 3. Colaboradores
create table if not exists collaborators (
  server_id text references servers(id) on delete cascade,
  user_id uuid not null,
  role text default 'viewer' check (role in ('admin', 'viewer')),
  invited_by uuid,
  created_at timestamptz default now(),
  primary key (server_id, user_id)
);

-- 4. Invitaciones (expiran a los 7 días)
create table if not exists invitations (
  id text primary key,
  server_id text references servers(id) on delete cascade,
  token text unique not null,
  created_by uuid not null,
  used boolean default false,
  expires_at timestamptz default now() + interval '7 days'
);

-- Índices
create index if not exists idx_servers_owner on servers(owner_id);
create index if not exists idx_changes_server on server_changes(server_id);
create index if not exists idx_collabs_user on collaborators(user_id);
create index if not exists idx_invitations_token on invitations(token);

-- 5. RLS (Row Level Security)
alter table servers enable row level security;
alter table server_changes enable row level security;
alter table collaborators enable row level security;
alter table invitations enable row level security;

-- Políticas: idempotentes (DROP IF EXISTS + CREATE)
-- El backend usa service_role key (bypass RLS),
-- pero si querés consultar directo desde el frontend
-- con la anon key, estas políticas protegen los datos.

drop policy if exists "Usuarios ven sus servidores" on servers;
create policy "Usuarios ven sus servidores"
  on servers for select
  using (owner_id = auth.uid());

drop policy if exists "Usuarios crean servidores" on servers;
create policy "Usuarios crean servidores"
  on servers for insert
  with check (owner_id = auth.uid());

drop policy if exists "Dueños actualizan sus servidores" on servers;
create policy "Dueños actualizan sus servidores"
  on servers for update
  using (owner_id = auth.uid());

drop policy if exists "Dueños eliminan sus servidores" on servers;
create policy "Dueños eliminan sus servidores"
  on servers for delete
  using (owner_id = auth.uid());

drop policy if exists "Cambios visibles para colaboradores" on server_changes;
create policy "Cambios visibles para colaboradores"
  on server_changes for select
  using (
    server_id in (
      select id from servers where owner_id = auth.uid()
      union
      select server_id from collaborators where user_id = auth.uid()
    )
  );

drop policy if exists "Colaboradores ven sus registros" on collaborators;
create policy "Colaboradores ven sus registros"
  on collaborators for select
  using (user_id = auth.uid());

drop policy if exists "Invitaciones visibles para el creador" on invitations;
create policy "Invitaciones visibles para el creador"
  on invitations for select
  using (created_by = auth.uid());
