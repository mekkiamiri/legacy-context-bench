package com.ex.model;

import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_user")
public class User {
    private String userName;
    private String passwordHash;

    public User(String userName) {
        this.userName = userName;
    }

    public String getPasswordHash() {
        return passwordHash;
    }
}
