create schema if not exists wilkerstat;
revoke all on schema wilkerstat from public, anon, authenticated;

create table if not exists wilkerstat.runs (
    id text primary key,
    snapshot bytea not null,
    created_at timestamptz not null default now()
);
create table if not exists wilkerstat.notes (
    run_id text not null references wilkerstat.runs(id),
    field text not null,
    value text not null,
    primary key(run_id, field)
);
create table if not exists wilkerstat.shared_files (
    name text primary key,
    contents bytea not null
);
create table if not exists wilkerstat.settings (
    name text primary key,
    value text not null
);
