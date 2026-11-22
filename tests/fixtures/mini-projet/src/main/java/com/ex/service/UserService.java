package com.ex.service;

public interface UserService {
    boolean authenticate(String userName, String password);

    String defaultSetting(String key);
}
