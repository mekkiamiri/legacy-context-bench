-- Schéma de l'application exemple
create table app_user (
    username varchar(64) not null primary key,
    passwordhash varchar(255)
);

create table app_settings (
    name varchar(255) not null primary key,
    value text
);
